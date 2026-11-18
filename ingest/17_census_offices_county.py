"""County-level ACS 5-year profile for the county of each Big 4 office, 2021 to latest.

Reads data/manual/big4_offices.csv (uses its county_fips) and pulls ACS 5-year county
data for each vintage in OFFICE_COUNTY_ACS_YEARS (default 2021-2024). One row per
office x acs_year. Needs CENSUS_API_KEY. Output: data/processed/acs_offices_county.parquet.

Connecticut: the 2022+ vintages use planning-region codes (e.g. 09110, 09190), but the
2021 vintage still uses the old counties, so those offices are mapped to the legacy
county for 2021 (see geo_note).
"""
import os

import numpy as np
import pandas as pd

from common import MANUAL, api_key, get_json, save, zfill_fips

YEARS = tuple(int(y) for y in os.getenv("OFFICE_COUNTY_ACS_YEARS", "").split(",") if y.strip()) or (2021, 2022, 2023, 2024)
CT_LEGACY_2021 = {"09110": "09003", "09190": "09001"}  # planning region -> legacy county

VARIABLES = {
    "B01003_001E": "population", "B01002_001E": "median_age",
    "B19013_001E": "median_hh_income", "B19301_001E": "per_capita_income",
    "B17001_001E": "poverty_universe", "B17001_002E": "below_poverty",
    "B15003_001E": "pop_25plus", "B15003_022E": "bachelors", "B15003_023E": "masters",
    "B15003_024E": "professional", "B15003_025E": "doctorate",
    "B23025_003E": "civilian_labor_force", "B23025_005E": "unemployed",
    "B25064_001E": "median_gross_rent", "B25077_001E": "median_home_value",
}


def fetch_state(year: int, state_fips: str, key: str) -> pd.DataFrame:
    url = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {"get": "NAME," + ",".join(VARIABLES), "for": "county:*", "in": f"state:{state_fips}", "key": key}
    rows = get_json(url, params)
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df["county_fips"] = df["state"] + df["county"]
    df = df.drop(columns=["state", "county"]).rename(columns={"NAME": "census_geo_name", **VARIABLES})
    for c in VARIABLES.values():
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df.loc[df[c] < -999999, c] = np.nan  # Census sentinel values (e.g. -666666666)
    return df


def main():
    key = api_key("CENSUS_API_KEY")
    offices = pd.read_csv(MANUAL / "big4_offices.csv", dtype=str)
    offices = offices[~offices["office_name"].str.startswith("EXAMPLE", na=False)].copy()
    offices["county_fips"] = zfill_fips(offices["county_fips"], 5)
    offices = offices[["firm", "office_name", "city", "state", "zip", "office_type", "county_fips"]]

    frames = []
    for year in YEARS:
        o = offices.copy()
        o["geo_note"] = ""
        if year == 2021:
            legacy = o["county_fips"].map(CT_LEGACY_2021)
            o["geo_note"] = np.where(legacy.notna(), "CT planning region mapped to legacy county for 2021", "")
            o["county_fips"] = legacy.fillna(o["county_fips"])
        census = pd.concat(
            [fetch_state(year, st, key) for st in sorted(o["county_fips"].str[:2].unique())], ignore_index=True
        )
        m = o.merge(census, on="county_fips", how="left")
        m.insert(0, "acs_year", year)
        frames.append(m)
        print(f"  {year}: {len(m)} rows, {m['census_geo_name'].isna().sum()} unmatched")

    df = pd.concat(frames, ignore_index=True)
    df["poverty_rate"] = (df["below_poverty"] / df["poverty_universe"]).round(4)
    df["bachelors_plus_rate"] = (
        (df[["bachelors", "masters", "professional", "doctorate"]].sum(axis=1, min_count=4) / df["pop_25plus"]).round(4)
    )
    df["unemployment_rate"] = (df["unemployed"] / df["civilian_labor_force"]).round(4)
    save(df, "acs_offices_county")


if __name__ == "__main__":
    main()
