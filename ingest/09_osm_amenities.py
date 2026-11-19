"""OpenStreetMap places for hobbies and daily life, counted per ZIP (ZCTA), for the ZIPs
within RADIUS_MILES (default 15) of a Big 4 office. Free Overpass API, no key.

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

How it works: a ZIP is in scope when its interior point is within RADIUS_MILES of any
office. For each metro, only the map tiles (<= TILE_DEG degrees) that touch its in-scope
ZIPs are queried, with every category in one request per tile. Each finished metro is
saved to data/raw/osm/<cbsa>.parquet, so re-runs skip it.

  python ingest/09_osm_amenities.py                # everything (laptop)
  python ingest/09_osm_amenities.py --shard 2/4    # download one quarter of the metros only
  python ingest/09_osm_amenities.py --combine      # build outputs from whatever is saved
  python ingest/09_osm_amenities.py 12420          # one metro (Austin), for a quick test

Outputs: osm_points.parquet (one row per place) and osm_amenities_zip.parquet/.csv
(counts and per-square-mile density per in-scope ZIP, plus miles to the nearest office).
Run 01_geography.py and 01b_offices.py first.
"""
import math
import os
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import box

from common import PROCESSED, RAW, save

RADIUS_MILES = float(os.getenv("OSM_RADIUS_MILES", "15"))
TILE_DEG = 0.4
# Overpass rejects browser-like User-Agents (HTTP 406), so identify the project honestly.
UA = {"User-Agent": "Big4CityRecommender/1.0 (McCombs MPA class project; "
                    f"{os.getenv('CONTACT_EMAIL') or 'github.com/mackscassandra/Case-2'})"}
SERVERS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.private.coffee/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter"]
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
CACHE = RAW / "osm"


def miles_to_nearest(lat, lon, olat, olon):
    """Great-circle miles from each (lat, lon) to the nearest office."""
    la, lo = np.radians(lat)[:, None], np.radians(lon)[:, None]
    ola, olo = np.radians(olat)[None, :], np.radians(olon)[None, :]
    a = np.sin((ola - la) / 2) ** 2 + np.cos(la) * np.cos(ola) * np.sin((olo - lo) / 2) ** 2
    return (2 * 3958.8 * np.arcsin(np.sqrt(a))).min(axis=1)


def scope() -> tuple[gpd.GeoDataFrame, dict]:
    """In-scope ZIPs (with nearest-office distance) and, per metro, the tiles to query."""
    offices = pd.read_parquet(PROCESSED / "offices.parquet")
    zcta = gpd.read_parquet(PROCESSED / "geo_zcta.parquet").dropna(subset=["lat", "lon"])
    zcta["miles_to_office"] = miles_to_nearest(zcta["lat"].values, zcta["lon"].values,
                                               offices["lat"].values, offices["lon"].values).round(1)
    near = zcta[zcta["miles_to_office"] <= RADIUS_MILES].copy()
    plan = {}
    for code, grp in offices.groupby("cbsa_code"):
        d = miles_to_nearest(near["lat"].values, near["lon"].values, grp["lat"].values, grp["lon"].values)
        mine = near[d <= RADIUS_MILES]
        if mine.empty:
            continue
        area = mine.geometry.union_all()
        minx, miny, maxx, maxy = area.bounds
        nx, ny = max(1, math.ceil((maxx - minx) / TILE_DEG)), max(1, math.ceil((maxy - miny) / TILE_DEG))
        dx, dy = (maxx - minx) / nx, (maxy - miny) / ny
        tiles = [(miny + j * dy, minx + i * dx, miny + (j + 1) * dy, minx + (i + 1) * dx)
                 for i in range(nx) for j in range(ny)]
        plan[code] = [t for t in tiles if box(t[1], t[0], t[3], t[2]).intersects(area)]
    return near, plan


def query(bbox) -> list[dict] | None:
    """Every category in one tile. Returns None if all servers failed."""
    s, w, n, e = bbox
    body = "".join(f"{sel}({s:.5f},{w:.5f},{n:.5f},{e:.5f});" for sel in SELECTORS)
    q = f"[out:json][timeout:180];({body});out center tags;"
    for attempt in range(3):
        for server in SERVERS:
            host = server.split("/")[2]
            try:
                r = requests.post(server, data={"data": q}, headers=UA, timeout=200)
                if r.status_code in (429, 502, 503, 504):
                    print(f"    {host} busy ({r.status_code})")
                    continue
                r.raise_for_status()
                js = r.json()
                if "error" in js.get("remark", "").lower():
                    raise requests.RequestException(js["remark"][:150])
                return js["elements"]
            except (requests.RequestException, ValueError) as ex:
                print(f"    {host} failed: {str(ex)[:150]}")
        time.sleep(20 * (attempt + 1))
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


def download(plan: dict, codes: list[str]) -> list[str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    failed = []
    for k, code in enumerate(codes, 1):
        out = CACHE / f"{code}.parquet"
        if out.exists():
            print(f"  [{k}/{len(codes)}] {code}: already saved")
            continue
        tiles = plan[code]
        print(f"  [{k}/{len(codes)}] {code}: {len(tiles)} tiles", flush=True)
        rows = []
        for t in tiles:
            els = query(t)
            if els is None:
                rows = None
                break
            rows += to_rows(els, code)
            time.sleep(1)
        if rows is None:
            print(f"    gave up on {code}; re-run to retry it")
            failed.append(code)
            continue
        df = pd.DataFrame(rows, columns=["osm_id", "category", "name", "lat", "lon", "cbsa_code"])
        df = df.drop_duplicates(["osm_id", "category"])
        df.to_parquet(out, index=False)
        print(f"    {len(df):,} places: " + ", ".join(f"{c} {n:,}" for c, n in df["category"].value_counts().items()))
    return failed


def combine(near: gpd.GeoDataFrame, plan: dict) -> list[str]:
    done = sorted(p.stem for p in CACHE.glob("*.parquet") if p.stem in plan)
    if not done:
        sys.exit("No metros downloaded yet")
    pts = pd.concat([pd.read_parquet(CACHE / f"{c}.parquet") for c in done], ignore_index=True)
    pts = pts.drop_duplicates(["osm_id", "category"]).reset_index(drop=True)  # neighboring metros overlap
    g = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.lon, pts.lat), crs="EPSG:4326")
    j = gpd.sjoin(g, near[["zcta", "geometry"]].to_crs(g.crs), predicate="within")
    j = j[~j.index.duplicated()]
    save(pts.loc[j.index].assign(zcta=j["zcta"].values), "osm_points")  # places inside in-scope ZIPs

    counts = (j.pivot_table(index="zcta", columns="category", values="osm_id", aggfunc="count", fill_value=0)
               .reindex(columns=CATEGORIES, fill_value=0))
    counts.columns = [f"n_{c}" for c in counts.columns]
    # A ZIP is covered when an office within the radius belongs to a downloaded metro
    offices = pd.read_parquet(PROCESSED / "offices.parquet")
    ok = offices[offices["cbsa_code"].isin(done)]
    d = miles_to_nearest(near["lat"].values, near["lon"].values, ok["lat"].values, ok["lon"].values)
    covered = pd.DataFrame(near[d <= RADIUS_MILES][["zcta", "cbsa_code", "land_sqmi", "miles_to_office"]])
    out = covered.merge(counts.reset_index(), on="zcta", how="left").fillna({f"n_{c}": 0 for c in CATEGORIES})
    for c in CATEGORIES:
        out[f"n_{c}"] = out[f"n_{c}"].astype(int)
        out[f"per_sqmi_{c}"] = (out[f"n_{c}"] / out["land_sqmi"].clip(lower=0.1)).round(3)
    out["radius_miles"] = RADIUS_MILES
    out["osm_pulled"] = pd.Timestamp.today().date().isoformat()
    out = out.sort_values("zcta")
    save(out, "osm_amenities_zip")
    out.to_csv(PROCESSED / "osm_amenities_zip.csv", index=False)
    missing = sorted(set(plan) - set(done))
    print(f"  {len(done)} of {len(plan)} metros, {len(out):,} ZIPs within {RADIUS_MILES:g} mi of an office")
    if missing:
        print(f"  not downloaded yet: {missing}")
    return missing


def main():
    near, plan = scope()
    total = sum(len(t) for t in plan.values())
    print(f"{len(near):,} ZIPs within {RADIUS_MILES:g} mi of an office; {len(plan)} metros, {total} tiles")
    args = sys.argv[1:]
    if "--combine" in args:
        sys.exit(1 if combine(near, plan) else 0)
    if "--shard" in args:
        k, n = map(int, args[args.index("--shard") + 1].split("/"))
        order = sorted(plan, key=lambda c: -len(plan[c]))  # deal biggest metros round-robin
        codes = [c for i, c in enumerate(order) if i % n == k - 1]
        print(f"shard {k}/{n}: {len(codes)} metros, {sum(len(plan[c]) for c in codes)} tiles")
        sys.exit(1 if download(plan, codes) else 0)
    codes = [a for a in args if a in plan] or sorted(plan)
    failed = download(plan, codes)
    combine(near, plan)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
