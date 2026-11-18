"""Join every processed dataset into the two tables the app reads:
  data/processed/zip_features.parquet    one row per ZIP (ZCTA)
  data/processed/metro_features.parquet  one row per metro (CBSA)
Missing datasets are skipped with a warning, so this runs at any stage.
"""
import pandas as pd

from common import PROCESSED, save


def load(name: str, cols=None) -> pd.DataFrame | None:
    p = PROCESSED / f"{name}.parquet"
    if not p.exists():
        print(f"  (missing {name}, skipped)")
        return None
    df = pd.read_parquet(p, columns=cols)
    return df.drop(columns="geometry", errors="ignore")


def join(base: pd.DataFrame, other: pd.DataFrame | None, key: str) -> pd.DataFrame:
    if other is None:
        return base
    other = other.drop(columns=[c for c in other.columns if c in base.columns and c != key])
    return base.merge(other, on=key, how="left")


def crime_by_metro() -> pd.DataFrame | None:
    c = load("fbi_crime_agency")
    if c is None:
        return None
    r = c[c["reported"] & c["population"].gt(0)]
    g = r.groupby("cbsa_code")
    out = pd.DataFrame({
        "violent_per_100k": g["violent_count"].sum() / g["population"].sum() * 1e5,
        "property_per_100k": g["property_count"].sum() / g["population"].sum() * 1e5,
        "crime_agencies_reporting": g.size(),
        "crime_agencies_total": c.groupby("cbsa_code").size(),
    }).reset_index()
    return out


def main():
    print("Building zip_features")
    z = load("geo_zcta", ["zcta", "land_sqmi", "lat", "lon", "county_fips", "state", "cbsa_code"])
    if z is None:
        raise SystemExit("Run 01_geography.py first")
    for name in ["acs_zcta", "zillow_zip", "epa_walkability_zip", "osm_amenities_zip", "google_cafes_zip",
                 "elections_zip"]:
        z = join(z, load(name), "zcta")
    for name in ["elections_county", "fema_nri_county"]:
        z = join(z, load(name), "county_fips")
    for name in ["bea_rpp_cbsa", "bls_accountant_wages_cbsa"]:
        z = join(z, load(name), "cbsa_code")
    save(z, "zip_features")

    print("Building metro_features")
    m = load("geo_cbsa", ["cbsa_code", "cbsa_name", "is_metro"])
    for name in ["acs_cbsa", "bea_rpp_cbsa", "bls_accountant_wages_cbsa"]:
        m = join(m, load(name), "cbsa_code")
    m = join(m, crime_by_metro(), "cbsa_code")
    # TODO: join acs_offices (from 12_census_offices.py) here. It is long-format
    #   (office x acs_year x level), so first pick the latest acs_year and level="tract",
    #   then aggregate per cbsa_code (needs cbsa_code on each office; it is a column in
    #   data/manual/big4_offices.csv) or join on county_fips.
    save(m, "metro_features")


if __name__ == "__main__":
    main()
