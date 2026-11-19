"""FBI Crime Data Explorer: violent and property crime for police agencies in target metros.

Needs FBI_API_KEY (free: https://api.data.gov/signup/). Docs:
https://cde.ucr.cjis.gov/LATEST/webapp/#/pages/docApi

The CDE API has changed paths more than once. Run `python 11_fbi_crime.py --probe`
first: it prints one raw response so you (or Claude Code) can adjust SUMMARY_PATH,
OFFENSES and parse() if the format differs. Crime is reported per agency, not per
neighborhood, and some agencies don't report; the output keeps a coverage flag.
"""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import geopandas as gpd
import pandas as pd
import requests

from common import HEADERS, PROCESSED, RAW, api_key, get_json, save

BASE = "https://api.usa.gov/crime/fbi/cde"
AGENCIES_PATH = "/agency/byStateAbbr/{state}"
SUMMARY_PATH = "/summarized/agency/{ori}/{offense}"
OFFENSES = {"V": "violent", "P": "property"}  # adjust after --probe if needed
YEAR = 2024
WORKERS = 6          # parallel requests; the API allowed this without throttling
CACHE = RAW / "fbi"  # one JSON per (agency, offense); a re-run only fetches what is missing
TIMEOUT = 30         # seconds per request; a hung connection must not stall the whole run
_session = threading.local()


def agencies(state: str) -> pd.DataFrame:
    js = get_json(BASE + AGENCIES_PATH.format(state=state), {"API_KEY": api_key("FBI_API_KEY")})
    rows = js if isinstance(js, list) else [a for v in js.values() for a in v]
    return pd.DataFrame(rows)


def summary(ori: str, offense: str, retries: int = 5):
    """Fetch one agency/offense summary, cached on disk. Returns None if it keeps failing."""
    path = CACHE / f"{ori}_{offense}.json"
    if path.exists():
        return json.loads(path.read_text())
    if not hasattr(_session, "s"):
        _session.s = requests.Session()
    url = BASE + SUMMARY_PATH.format(ori=ori, offense=offense)
    params = {"from": f"01-{YEAR}", "to": f"12-{YEAR}", "API_KEY": api_key("FBI_API_KEY")}
    for attempt in range(1, retries + 1):
        try:
            r = _session.s.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 5 * attempt)))
                continue
            if r.status_code == 404:   # agency has no data for this offense
                js = {}
            else:
                r.raise_for_status()
                js = r.json()
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(js))
            return js
        except (requests.RequestException, ValueError):
            time.sleep(2 * attempt)
    return None


def parse(js, agency_name: str | None = None) -> tuple[float | None, float | None]:
    """Return (annual offense count, population) for this agency.

    The response also holds state and US series ("Texas Offenses", "United States ..."),
    so pick the series named after the agency, not just the first one.
    """
    try:
        actuals = js["offenses"]["actuals"]
        key = f"{agency_name} Offenses"
        if key not in actuals:  # name mismatch: take the series that is not state/US/clearances
            skip = ("United States", "Clearances")
            cands = [k for k in actuals if k.endswith("Offenses") and not k.startswith(skip)]
            if len(cands) != 1:
                return None, None
            key = cands[0]
        count = sum(x for x in actuals[key].values() if x is not None)
        pops = js.get("populations", {}).get("population", {})
        pop = pops.get(key[: -len(" Offenses")], {})
        pop_val = max(pop.values()) if isinstance(pop, dict) and pop else None
        return count, pop_val
    except (KeyError, TypeError, AttributeError):
        return None, None


def fetch_agency(a) -> dict:
    rec = {"ori": a.ori, "agency_name": getattr(a, "agency_name", None), "cbsa_code": a.cbsa_code,
           "lat": a.latitude, "lon": a.longitude, "population": None}
    for code, label in OFFENSES.items():
        js = summary(a.ori, code)
        count, pop = parse(js, rec["agency_name"]) if js else (None, None)
        rec[f"{label}_count"] = count
        rec["population"] = pop or rec["population"]
    return rec


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

    rows, done, t0 = [], 0, time.time()
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(fetch_agency, a) for a in g.itertuples()]
        for f in as_completed(futures):
            rows.append(f.result())
            done += 1
            if done % 250 == 0 or done == len(futures):
                rate = done / (time.time() - t0)
                print(f"  {done:,}/{len(futures):,} agencies ({rate:.1f}/s, "
                      f"~{(len(futures) - done) / rate / 60:.0f} min left)", flush=True)
    df = pd.DataFrame(rows)
    for label in OFFENSES.values():
        df[f"{label}_per_100k"] = df[f"{label}_count"] / df["population"] * 100_000
    df["reported"] = df["violent_count"].notna()
    df["crime_year"] = YEAR
    save(df, "fbi_crime_agency")


if __name__ == "__main__":
    main()
