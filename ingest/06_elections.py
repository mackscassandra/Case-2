"""2024 presidential results by county (display-only layer; not used in scoring).

Source: tonmcg/US_County_Level_Election_Results_08-24 on GitHub (compiled from
state and media results). Cross-check against MIT Election Data + Science Lab
(https://electionlab.mit.edu/data) before the final demo. No key needed.
"""
import pandas as pd

from common import RAW, download, save, zfill_fips

URL = ("https://raw.githubusercontent.com/tonmcg/US_County_Level_Election_Results_08-24/"
       "master/2024_US_County_Level_Presidential_Results.csv")


def main():
    print("County presidential results 2024")
    df = pd.read_csv(download(URL, RAW / "elections" / "county_pres_2024.csv"))
    out = pd.DataFrame({
        "county_fips": zfill_fips(df["county_fips"], 5),
        "total_votes": df["total_votes"],
        "pct_gop": df["per_gop"],
        "pct_dem": df["per_dem"],
    })
    out["margin_dem_minus_gop"] = out["pct_dem"] - out["pct_gop"]
    out["election_year"] = 2024
    save(out, "elections_county")


if __name__ == "__main__":
    main()
