"""Big 4 office list -> offices.parquet with metro (CBSA) and county codes.

Reads data/manual/big4_offices.csv (hand-maintained) and places each office in the
metro and county that contain its lat/lon. A cbsa_code typed into the CSV wins over
the computed one. Run 01_geography.py first. No key needed.
"""
import geopandas as gpd
import pandas as pd

from common import MANUAL, PROCESSED, save


def main():
    print("Big 4 offices -> metros")
    df = pd.read_csv(MANUAL / "big4_offices.csv", dtype=str)
    df = df[~df["office_name"].str.startswith("EXAMPLE", na=False)]
    df["lat"], df["lon"] = pd.to_numeric(df["lat"]), pd.to_numeric(df["lon"])

    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
    cbsa = gpd.read_parquet(PROCESSED / "geo_cbsa.parquet")[["cbsa_code", "cbsa_name", "geometry"]]
    county = gpd.read_parquet(PROCESSED / "geo_county.parquet")[["county_fips", "geometry"]]
    pts = gpd.sjoin(pts, cbsa.rename(columns={"cbsa_code": "cbsa_calc"}), how="left", predicate="within").drop(columns="index_right")
    pts = gpd.sjoin(pts, county, how="left", predicate="within").drop(columns="index_right")
    pts = pts.drop_duplicates(["firm", "office_name", "address"])

    pts["cbsa_code"] = pts["cbsa_code"].where(pts["cbsa_code"].notna() & pts["cbsa_code"].ne(""), pts["cbsa_calc"])
    out = pd.DataFrame(pts.drop(columns=["geometry", "cbsa_calc"]))
    miss = out[out["cbsa_code"].isna()]
    print(f"  {len(out)} offices in {out['cbsa_code'].nunique()} metros; {len(miss)} outside any metro:")
    for r in miss.head(25).itertuples():
        print(f"    {r.firm} {r.office_name} ({r.city}, {r.state})")
    save(out, "offices")
    out.to_csv(PROCESSED / "offices.csv", index=False)  # browsable copy for GitHub


if __name__ == "__main__":
    main()
