"""OpenStreetMap amenities (cafes, restaurants, gyms, parks, bars, childcare, trails)
for each target metro, via the free Overpass API. Counts per ZIP and per square mile.

Target metros = the CBSAs in data/manual/big4_offices.csv. Until that file is filled
in, the script falls back to the 50 largest metros by population (needs acs_cbsa).
Run 01_geography.py first. Be polite: one metro at a time with pauses.
"""
import sys
import time

import geopandas as gpd
import pandas as pd
import requests

from common import HEADERS, MANUAL, PROCESSED, RAW, save

SERVERS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter"]
CATEGORIES = {
    "cafe": ['nwr["amenity"="cafe"]', 'nwr["shop"="coffee"]'],
    "restaurant": ['nwr["amenity"~"^(restaurant|fast_food)$"]'],
    "bar": ['nwr["amenity"~"^(bar|pub|nightclub)$"]'],
    "gym": ['nwr["leisure"="fitness_centre"]'],
    "park": ['nwr["leisure"="park"]'],
    "childcare": ['nwr["amenity"~"^(childcare|kindergarten)$"]'],
    "trail": ['relation["route"="hiking"]'],
}


def target_metros(cbsa: gpd.GeoDataFrame) -> list[str]:
    offices = PROCESSED / "offices.parquet"  # built by 01b_offices.py
    if offices.exists():
        codes = pd.read_parquet(offices, columns=["cbsa_code"])["cbsa_code"].dropna().unique().tolist()
        if codes:
            return codes
    print("  offices.parquet not found (run 01b_offices.py); using the 50 largest metros")
    acs = pd.read_parquet(PROCESSED / "acs_cbsa.parquet")
    return acs.nlargest(50, "pop_total")["cbsa_code"].tolist()


def query(bbox: tuple, category: str) -> list[dict]:
    s, w, n, e = bbox
    body = "".join(f'{sel}({s},{w},{n},{e});' for sel in CATEGORIES[category])
    q = f"[out:json][timeout:300];({body});out center tags;"
    for server in SERVERS:
        try:
            r = requests.post(server, data={"data": q}, headers=HEADERS, timeout=360)
            if r.status_code == 429:
                time.sleep(60)
                continue
            r.raise_for_status()
            return r.json()["elements"]
        except requests.RequestException as ex:
            print(f"    {server} failed: {ex}")
    return []


def main():
    cbsa = gpd.read_parquet(PROCESSED / "geo_cbsa.parquet")
    zcta = gpd.read_parquet(PROCESSED / "geo_zcta.parquet")
    codes = sys.argv[1:] or target_metros(cbsa)
    cache = RAW / "osm"
    cache.mkdir(parents=True, exist_ok=True)

    points = []
    for code in codes:
        row = cbsa[cbsa["cbsa_code"] == code]
        if row.empty:
            print(f"  unknown CBSA {code}, skipping")
            continue
        minx, miny, maxx, maxy = row.total_bounds
        out = cache / f"{code}.parquet"
        if out.exists():
            points.append(pd.read_parquet(out))
            continue
        print(f"  {code} {row['cbsa_name'].iloc[0]}")
        rows = []
        for cat in CATEGORIES:
            for el in query((miny, minx, maxy, maxx), cat):
                lat = el.get("lat") or el.get("center", {}).get("lat")
                lon = el.get("lon") or el.get("center", {}).get("lon")
                if lat is None:
                    continue
                rows.append({"osm_id": f"{el['type']}/{el['id']}", "category": cat,
                             "name": el.get("tags", {}).get("name"), "lat": lat, "lon": lon,
                             "cbsa_code": code})
            time.sleep(2)
        df = pd.DataFrame(rows).drop_duplicates(["osm_id", "category"])
        df.to_parquet(out, index=False)
        points.append(df)

    pts = pd.concat(points, ignore_index=True)
    save(pts, "osm_points")

    g = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.lon, pts.lat), crs="EPSG:4326")
    j = gpd.sjoin(g, zcta[["zcta", "geometry"]].to_crs(g.crs), predicate="within")
    counts = j.pivot_table(index="zcta", columns="category", values="osm_id", aggfunc="count", fill_value=0)
    counts.columns = [f"n_{c}" for c in counts.columns]
    counts = counts.reset_index().merge(zcta[["zcta", "land_sqmi"]], on="zcta")
    for c in [c for c in counts.columns if c.startswith("n_")]:
        counts[c.replace("n_", "per_sqmi_")] = counts[c] / counts["land_sqmi"].clip(lower=0.1)
    save(counts.drop(columns="land_sqmi"), "osm_amenities_zip")


if __name__ == "__main__":
    main()
