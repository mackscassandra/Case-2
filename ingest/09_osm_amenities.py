"""OpenStreetMap places for hobbies and daily life, counted per ZIP (ZCTA), for every
metro with a Big 4 office. Free Overpass API, no key.

Categories (OSM tags):
  cafe        amenity=cafe, shop=coffee
  restaurant  amenity=restaurant|fast_food
  bar         amenity=bar|pub|nightclub
  gym         leisure=fitness_centre
  sports      leisure=sports_centre
  park        leisure=park
  dog_park    leisure=dog_park
  nature      leisure=nature_reserve
  trail       route=hiking (relations)
  culture     amenity=cinema|theatre|arts_centre, tourism=museum
  childcare   amenity=childcare|kindergarten

Each metro's bounding box is split into tiles (<= TILE_DEG degrees a side) and every
category is fetched in one query per tile. A metro is cached in data/raw/osm/ only when
all its tiles succeed, so re-running fills gaps without re-downloading. Points are
de-duplicated across overlapping metros before counting.

Outputs: osm_points.parquet (one row per place), osm_amenities_zip.parquet/.csv
(counts and per-square-mile density per ZIP). Run 01_geography.py and 01b_offices.py first.
  python ingest/09_osm_amenities.py            # all Big 4 metros
  python ingest/09_osm_amenities.py 12420      # just Austin, for a quick test
"""
import math
import sys
import time

import geopandas as gpd
import pandas as pd
import requests

from common import HEADERS, PROCESSED, RAW, save

SERVERS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter",
           "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
TILE_DEG = 0.6
SELECTORS = [
    'nwr["amenity"~"^(cafe|restaurant|fast_food|bar|pub|nightclub|cinema|theatre|arts_centre|childcare|kindergarten)$"]',
    'nwr["shop"="coffee"]',
    'nwr["leisure"~"^(fitness_centre|sports_centre|park|dog_park|nature_reserve)$"]',
    'nwr["tourism"="museum"]',
    'relation["route"="hiking"]',
]
CATEGORY_OF = {
    ("amenity", "cafe"): "cafe", ("shop", "coffee"): "cafe",
    ("amenity", "restaurant"): "restaurant", ("amenity", "fast_food"): "restaurant",
    ("amenity", "bar"): "bar", ("amenity", "pub"): "bar", ("amenity", "nightclub"): "bar",
    ("leisure", "fitness_centre"): "gym", ("leisure", "sports_centre"): "sports",
    ("leisure", "park"): "park", ("leisure", "dog_park"): "dog_park",
    ("leisure", "nature_reserve"): "nature", ("route", "hiking"): "trail",
    ("amenity", "cinema"): "culture", ("amenity", "theatre"): "culture",
    ("amenity", "arts_centre"): "culture", ("tourism", "museum"): "culture",
    ("amenity", "childcare"): "childcare", ("amenity", "kindergarten"): "childcare",
}
CATEGORIES = sorted(set(CATEGORY_OF.values()))


def target_metros() -> list[str]:
    offices = PROCESSED / "offices.parquet"  # built by 01b_offices.py
    if not offices.exists():
        sys.exit("offices.parquet not found: run 01_geography.py and 01b_offices.py first")
    return sorted(pd.read_parquet(offices, columns=["cbsa_code"])["cbsa_code"].dropna().unique())


def tiles(minx, miny, maxx, maxy):
    nx, ny = max(1, math.ceil((maxx - minx) / TILE_DEG)), max(1, math.ceil((maxy - miny) / TILE_DEG))
    dx, dy = (maxx - minx) / nx, (maxy - miny) / ny
    for i in range(nx):
        for j in range(ny):
            yield (miny + j * dy, minx + i * dx, miny + (j + 1) * dy, minx + (i + 1) * dx)


def query(bbox) -> list[dict] | None:
    """All categories in one tile. Returns None if every server failed."""
    s, w, n, e = bbox
    body = "".join(f"{sel}({s:.5f},{w:.5f},{n:.5f},{e:.5f});" for sel in SELECTORS)
    q = f"[out:json][timeout:600];({body});out center tags;"
    for attempt in range(3):
        for server in SERVERS:
            try:
                r = requests.post(server, data={"data": q}, headers=HEADERS, timeout=660)
                if r.status_code in (429, 504):
                    time.sleep(30 * (attempt + 1))
                    continue
                r.raise_for_status()
                js = r.json()
                if "remark" in js and "error" in js["remark"].lower():
                    raise requests.RequestException(js["remark"][:200])
                return js["elements"]
            except (requests.RequestException, ValueError) as ex:
                print(f"    {server.split('/')[2]} failed: {str(ex)[:120]}")
                time.sleep(5)
    return None


def to_rows(elements, code):
    rows = []
    for el in elements:
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None:
            continue
        for (k, v), cat in CATEGORY_OF.items():
            if tags.get(k) == v:
                rows.append({"osm_id": f"{el['type']}/{el['id']}", "category": cat,
                             "name": tags.get("name"), "lat": lat, "lon": lon, "cbsa_code": code})
    return rows


def main():
    cbsa = gpd.read_parquet(PROCESSED / "geo_cbsa.parquet")
    zcta = gpd.read_parquet(PROCESSED / "geo_zcta.parquet")
    codes = sys.argv[1:] or target_metros()
    cache = RAW / "osm"
    cache.mkdir(parents=True, exist_ok=True)

    points, failed, done = [], [], []
    for k, code in enumerate(codes, 1):
        row = cbsa[cbsa["cbsa_code"] == code]
        if row.empty:
            print(f"  unknown CBSA {code}, skipping")
            continue
        out = cache / f"{code}.parquet"
        if out.exists():
            points.append(pd.read_parquet(out))
            done.append(code)
            continue
        name = row["cbsa_name"].iloc[0]
        ts = list(tiles(*row.total_bounds))
        print(f"  [{k}/{len(codes)}] {code} {name}: {len(ts)} tiles", flush=True)
        rows, ok = [], True
        for t in ts:
            els = query(t)
            if els is None:
                ok = False
                break
            rows += to_rows(els, code)
            time.sleep(2)
        if not ok:
            print(f"    gave up on {name}; re-run to retry it")
            failed.append(code)
            continue
        df = pd.DataFrame(rows, columns=["osm_id", "category", "name", "lat", "lon", "cbsa_code"])
        df = df.drop_duplicates(["osm_id", "category"])
        print(f"    {len(df):,} places: " + ", ".join(f"{c} {n:,}" for c, n in df["category"].value_counts().items()))
        df.to_parquet(out, index=False)
        points.append(df)
        done.append(code)

    pts = pd.concat(points, ignore_index=True)
    pts = pts.drop_duplicates(["osm_id", "category"])  # metro boxes overlap
    save(pts, "osm_points")

    g = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.lon, pts.lat), crs="EPSG:4326")
    j = gpd.sjoin(g, zcta[["zcta", "geometry"]].to_crs(g.crs), predicate="within")
    counts = (j.pivot_table(index="zcta", columns="category", values="osm_id", aggfunc="count", fill_value=0)
               .reindex(columns=CATEGORIES, fill_value=0))
    counts.columns = [f"n_{c}" for c in counts.columns]
    # Every ZIP inside a covered metro gets a row, including ones with zero places
    covered = zcta[zcta["cbsa_code"].isin(done)][["zcta", "cbsa_code", "land_sqmi"]]
    counts = covered.merge(counts.reset_index(), on="zcta", how="left").fillna(
        {f"n_{c}": 0 for c in CATEGORIES})
    for c in CATEGORIES:
        counts[f"n_{c}"] = counts[f"n_{c}"].astype(int)
        counts[f"per_sqmi_{c}"] = (counts[f"n_{c}"] / counts["land_sqmi"].clip(lower=0.1)).round(3)
    counts["osm_pulled"] = pd.Timestamp.today().date().isoformat()
    save(counts, "osm_amenities_zip")
    counts.to_csv(PROCESSED / "osm_amenities_zip.csv", index=False)

    print(f"  {counts['cbsa_code'].nunique()} metros, {len(counts):,} ZIPs")
    if failed:
        print(f"  FAILED metros (re-run to retry): {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
