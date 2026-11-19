"""FBI Crime Data Explorer: violent and property crime for police agencies in target metros.

Needs FBI_API_KEY (free: https://api.data.gov/signup/). Docs:
https://cde.ucr.cjis.gov/LATEST/webapp/#/pages/docApi

The CDE API has changed paths more than once. Run `python 11_fbi_crime.py --probe`
first: it prints one raw response so you (or Claude Code) can adjust SUMMARY_PATH,
OFFENSES and parse() if the format differs. Crime is reported per agency, not per
neighborhood, and some agencies don't report; the output keeps a coverage flag.
"""
import sys

import geopandas as gpd
import pandas as pd

from common import PROCESSED, api_key, get_json, save

BASE = "https://api.usa.gov/crime/fbi/cde"
AGENCIES_PATH = "/agency/byStateAbbr/{state}"
SUMMARY_PATH = "/summarized/agency/{ori}/{offense}"
OFFENSES = {"V": "violent", "P": "property"}  # adjust after --probe if needed
YEAR = 2024


def agencies(state: str) -> pd.DataFrame:
    js = get_json(BASE + AGENCIES_PATH.format(state=state), {"API_KEY": api_key("FBI_API_KEY")})
    rows = js if isinstance(js, list) else [a for v in js.values() for a in v]
    return pd.DataFrame(rows)


def summary(ori: str, offense: str):
    return get_json(BASE + SUMMARY_PATH.format(ori=ori, offense=offense),
                    {"from": f"01-{YEAR}", "to": f"12-{YEAR}", "API_KEY": api_key("FBI_API_KEY")})


def parse(js) -> tuple[float | None, float | None]:
    """Return (annual offense count, population covered). Adjust to the --probe output."""
    try:
        actuals = js["offenses"]["actuals"]
        series = next(v for k, v in actuals.items() if "Clearances" not in k)
        count = sum(x for x in series.values() if x is not None)
        pops = js.get("populations", {}).get("population", {})
        pop = next(iter(pops.values()), {}) if pops else {}
        pop_val = max(pop.values()) if isinstance(pop, dict) and pop else None
        return count, pop_val
    except (KeyError, StopIteration, TypeError):
        return None, None


def main():
    cbsa = gpd.read_parquet(PROCESSED / "geo_cbsa.parquet")
    county = gpd.read_parquet(PROCESSED / "geo_county.parquet")
    # Crime is scored per metro, so use the metros that have a Big 4 office (from 01b_offices.py).
    metros = pd.read_parquet(PROCESSED / "offices.parquet", columns=["cbsa_code"])["cbsa_code"].dropna().unique()
    states = sorted(county["state"].dropna().unique())

    if "--probe" in sys.argv:
        a = agencies("TX")
        print(a.head(3).T)
        ori = a.iloc[0]["ori"]
        print(summary(ori, list(OFFENSES)[0]))
        return

    ag = pd.concat([agencies(s) for s in states], ignore_index=True)
    ag = ag.dropna(subset=["latitude", "longitude"])
    g = gpd.GeoDataFrame(ag, geometry=gpd.points_from_xy(ag.longitude, ag.latitude), crs="EPSG:4326")
    g = gpd.sjoin(g, cbsa[cbsa["cbsa_code"].isin(metros)][["cbsa_code", "geometry"]], predicate="within")
    print(f"  {len(g):,} agencies inside target metros")

    rows = []
    for a in g.itertuples():
        rec = {"ori": a.ori, "agency_name": getattr(a, "agency_name", None), "cbsa_code": a.cbsa_code,
               "lat": a.latitude, "lon": a.longitude}
        for code, label in OFFENSES.items():
            count, pop = parse(summary(a.ori, code))
            rec[f"{label}_count"], rec["population"] = count, pop or rec.get("population")
        rows.append(rec)
    df = pd.DataFrame(rows)
    for label in OFFENSES.values():
        df[f"{label}_per_100k"] = df[f"{label}_count"] / df["population"] * 100_000
    df["reported"] = df["violent_count"].notna()
    df["crime_year"] = YEAR
    save(df, "fbi_crime_agency")


if __name__ == "__main__":
    main()
