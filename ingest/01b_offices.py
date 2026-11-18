"""Big 4 office list -> offices.parquet with metro (CBSA) and county codes.

Reads data/manual/big4_offices.csv (hand-maintained) and places each office in the
metro and county that contain its lat/lon. Codes already typed into the CSV win over
computed ones, so the step only fills blanks (e.g. a newly added office). It then
writes cbsa_code, cbsa_name and county_fips back into the CSV, keeping column order.
Run 01_geography.py first. No key needed.
"""
import geopandas as gpd
import pandas as pd

from common import MANUAL, PROCESSED, save

CODES = ["cbsa_code", "cbsa_name", "county_fips"]


def blank(s: pd.Series) -> pd.Series:
    return s.isna() | s.astype(str).str.strip().eq("")


def main():
    print("Big 4 offices -> metros")
    path = MANUAL / "big4_offices.csv"
    manual = pd.read_csv(path, dtype=str, keep_default_na=False)
    for c in CODES:
        if c not in manual:
            manual[c] = ""

    df = manual[~manual["office_name"].str.startswith("EXAMPLE")].copy()
    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(pd.to_numeric(df["lon"]), pd.to_numeric(df["lat"])),
                           crs="EPSG:4326")
    cbsa = gpd.read_parquet(PROCESSED / "geo_cbsa.parquet")[["cbsa_code", "cbsa_name", "geometry"]]
    county = gpd.read_parquet(PROCESSED / "geo_county.parquet")[["county_fips", "geometry"]]
    pts = gpd.sjoin(pts, cbsa.add_suffix("_calc").set_geometry("geometry_calc"), how="left",
                    predicate="within").drop(columns="index_right")
    pts = gpd.sjoin(pts, county.add_suffix("_calc").set_geometry("geometry_calc"), how="left",
                    predicate="within").drop(columns="index_right")
    pts = pts[~pts.index.duplicated()]

    # Fill only blanks; names follow the final code so they always match it
    for c in ["cbsa_code", "county_fips"]:
        df[c] = df[c].where(~blank(df[c]), pts[f"{c}_calc"]).fillna("")
    names = dict(zip(cbsa["cbsa_code"], cbsa["cbsa_name"]))
    df["cbsa_name"] = df["cbsa_name"].where(~blank(df["cbsa_name"]), df["cbsa_code"].map(names)).fillna("")

    miss = df[blank(df["cbsa_code"])]
    print(f"  {len(df)} offices in {df['cbsa_code'].replace('', pd.NA).nunique()} metros; "
          f"{len(miss)} outside any metro")
    for r in miss.head(25).itertuples():
        print(f"    {r.firm} {r.office_name} ({r.city}, {r.state})")

    out = df.copy()
    out["lat"], out["lon"] = pd.to_numeric(out["lat"]), pd.to_numeric(out["lon"])
    save(out, "offices")
    out.to_csv(PROCESSED / "offices.csv", index=False)  # browsable copy for GitHub

    manual.loc[df.index, CODES] = df[CODES]
    manual.to_csv(path, index=False)
    print("  filled any blank cbsa_code / cbsa_name / county_fips in data/manual/big4_offices.csv")


if __name__ == "__main__":
    main()
