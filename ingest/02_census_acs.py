"""Census American Community Survey (5-year) for ZIPs (ZCTA) and metros (CBSA).

Needs CENSUS_API_KEY (free: https://api.census.gov/data/key_signup.html).
Set ACS_YEAR in .env to change the survey year (default 2024 = 2020-2024 data).
"""
import os

import pandas as pd

from common import api_key, get_json, save

YEAR = int(os.getenv("ACS_YEAR", "2024"))

VARS = {
    "B01003_001E": "pop_total",
    # Ages 22-34 (male then female) -> young-professional share
    "B01001_010E": "m22_24", "B01001_011E": "m25_29", "B01001_012E": "m30_34",
    "B01001_034E": "f22_24", "B01001_035E": "f25_29", "B01001_036E": "f30_34",
    # Education, population 25+
    "B15003_001E": "pop25", "B15003_022E": "ed_ba", "B15003_023E": "ed_ma",
    "B15003_024E": "ed_prof", "B15003_025E": "ed_phd",
    # Money
    "B19013_001E": "median_hh_income",
    "B25064_001E": "median_gross_rent",
    "B25077_001E": "median_home_value",
    "B25103_001E": "median_property_tax",
    # Households with children
    "B11005_001E": "households", "B11005_002E": "hh_with_kids",
    # Commuting
    "B08013_001E": "agg_travel_min", "B08012_001E": "commuters",
    "B08301_001E": "workers", "B08301_010E": "work_transit",
    "B08301_019E": "work_walk", "B08301_021E": "work_home",
}

GEOS = {
    "zcta": ("zip code tabulation area:*", "zip code tabulation area"),
    "cbsa": ("metropolitan statistical area/micropolitan statistical area:*",
             "metropolitan statistical area/micropolitan statistical area"),
}


def fetch(geo: str) -> pd.DataFrame:
    for_clause, id_col = GEOS[geo]
    url = f"https://api.census.gov/data/{YEAR}/acs/acs5"
    rows = get_json(url, {"get": "NAME," + ",".join(VARS), "for": for_clause,
                          "key": api_key("CENSUS_API_KEY")})
    df = pd.DataFrame(rows[1:], columns=rows[0]).rename(columns=VARS)
    df = df.rename(columns={id_col: geo if geo == "zcta" else "cbsa_code", "NAME": "acs_name"})
    num = list(VARS.values())
    df[num] = df[num].apply(pd.to_numeric, errors="coerce")
    df[num] = df[num].mask(df[num] < 0)  # Census uses -666666666 etc. for "not available"
    return derive(df)


def derive(df: pd.DataFrame) -> pd.DataFrame:
    young = df[["m22_24", "m25_29", "m30_34", "f22_24", "f25_29", "f30_34"]].sum(axis=1)
    grad = df[["ed_ba", "ed_ma", "ed_prof", "ed_phd"]].sum(axis=1)
    out = df.copy()
    out["pct_age_22_34"] = young / df["pop_total"]
    out["pct_bachelors_plus"] = grad / df["pop25"]
    out["pct_hh_with_kids"] = df["hh_with_kids"] / df["households"]
    out["mean_commute_min"] = df["agg_travel_min"] / df["commuters"]
    out["pct_transit"] = df["work_transit"] / df["workers"]
    out["pct_walk"] = df["work_walk"] / df["workers"]
    out["pct_work_home"] = df["work_home"] / df["workers"]
    out["acs_year"] = YEAR
    drop = ["m22_24", "m25_29", "m30_34", "f22_24", "f25_29", "f30_34", "ed_ba", "ed_ma",
            "ed_prof", "ed_phd", "agg_travel_min", "hh_with_kids", "work_transit", "work_walk", "work_home"]
    return out.drop(columns=drop)


def main():
    for geo in GEOS:
        print(f"ACS {YEAR} by {geo}")
        save(fetch(geo), f"acs_{geo}")


if __name__ == "__main__":
    main()
