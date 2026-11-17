"""Neighborhood ACS profile around each Big 4 office, for five ACS 5-year vintages.

Reads data/manual/big4_offices.csv, geocodes each office with the free Census
Geocoder (lat/lon in the CSV are used if present, otherwise the street address),
then pulls ACS for the office's tract, county and state.

Needs CENSUS_API_KEY. Set OFFICE_ACS_YEARS in .env (comma-separated) to change
the vintages (default 2020-2024). Output: one row per office x year x level,
keyed by firm + office_name, with state_fips / county_fips / tract_fips join keys.
"""
import os
import sys

import pandas as pd

from common import MANUAL, ROOT, api_key, save

sys.path.insert(0, str(ROOT))  # reuse the standalone census/ package
from census import CensusClient  # noqa: E402
from census.office import DEFAULT_YEARS, office_profile  # noqa: E402

YEARS = tuple(int(y) for y in os.getenv("OFFICE_ACS_YEARS", "").split(",") if y.strip()) or DEFAULT_YEARS


def office_rows(office: pd.Series, client: CensusClient) -> list[dict]:
    has_pt = pd.notna(office.get("lat")) and pd.notna(office.get("lon"))
    if has_pt:
        prof = office_profile(lat=float(office["lat"]), lon=float(office["lon"]), years=YEARS, client=client)
    else:
        addr = f"{office['address']}, {office['city']}, {office['state']} {office['zip']}"
        prof = office_profile(address=addr, years=YEARS, client=client)
    loc = prof["location"]
    base = {
        "firm": office["firm"], "office_name": office["office_name"],
        "state_fips": loc["state"], "county_fips": loc["state"] + loc["county"],
        "tract_fips": loc["state"] + loc["county"] + loc["tract"],
    }
    rows = []
    for year, by_level in prof["years"].items():
        if "error" in by_level:
            print(f"  {office['office_name']} {year}: {by_level['error']}")
            continue
        for level in ("tract", "county", "state"):
            d = by_level[level]
            rows.append({**base, "acs_year": year, "level": level, "acs_name": d["name"],
                         **{k: v for k, v in d.items() if k != "name"}})
    return rows


def main():
    offices = pd.read_csv(MANUAL / "big4_offices.csv", dtype=str)
    offices = offices[~offices["office_name"].str.startswith("EXAMPLE", na=False)]
    if offices.empty:
        raise SystemExit("data/manual/big4_offices.csv has no real offices yet (only the EXAMPLE row).")
    client = CensusClient(api_key=api_key("CENSUS_API_KEY"))
    rows = []
    for _, office in offices.iterrows():
        print(f"{office['firm']} - {office['office_name']}")
        try:
            rows += office_rows(office, client)
        except Exception as e:  # one bad address shouldn't stop the rest
            print(f"  skipped: {type(e).__name__}: {e}")
    if not rows:
        raise SystemExit("No office rows produced.")
    save(pd.DataFrame(rows), "acs_offices")


if __name__ == "__main__":
    main()
