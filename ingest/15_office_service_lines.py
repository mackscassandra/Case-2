"""Code the audit / tax / advisory columns of big4_offices.csv from real job postings.

Rule: an office gets 1 for a service line if its firm posted at least MIN_POSTINGS
jobs in that service line in the office's metro (CBSA) since 2022, else 0. Postings
name a city, not an office, so every main office of a firm in one metro gets the
same codes. Specialty sites (office_type = "specialty": Deloitte Digital studios,
EY wavespace, Deloitte University, ...) are left blank for the team to code by hand.

Input: data/processed/wagescape/jobs_big4*.parquet (from 14_wagescape_jobs.py).
  python ingest/15_office_service_lines.py --inspect   # print columns + samples, change nothing
  python ingest/15_office_service_lines.py             # code the CSV
Also writes data/processed/office_service_postings.csv with the posting counts behind
every 1 and 0, so each code can be checked.
"""
import os
import re
import sys

import pandas as pd

from common import MANUAL, PROCESSED

MIN_POSTINGS = int(os.getenv("SERVICE_MIN_POSTINGS", "3"))
SRC = PROCESSED / "wagescape"
LINES = ["audit", "tax", "advisory"]

# Keywords checked against title (+ job family / description when present), in order.
# Tax first: "tax technology consultant" is Tax; "IT audit" is Audit (assurance).
PATTERNS = {
    "tax": r"\btax(?:es|ation)?\b|\bvat\b|transfer pricing|\bsalt\b|indirect tax|international tax",
    "audit": r"\baudit(?:or|ors|ing)?\b|\bassurance\b|attest|\bsox\b|financial statement|\bcaas\b",
    "advisory": r"advis|consult|\bdeals?\b|transaction|valuation|forensic|\brisk\b|cyber|strategy|"
                r"technology|transformation|\bm&a\b|restructuring|analytics|implementation|parthenon",
}
COLS = {
    "company": ["COMPANY_STD"],
    "title": ["TITLE", "JOB_TITLE", "POSITION_TITLE", "TITLE_RAW"],
    "family": ["JOB_FAMILY", "SUB_JOB_FAMILY", "ROLE_PRIMARY", "CATEGORY", "DEPARTMENT"],
    "desc": ["DESCRIPTION", "JOB_DESCRIPTION", "DESCRIPTION_TEXT"],
    "city": ["CITY", "LOCATION_CITY", "JOB_CITY"],
    "state": ["STATE", "STATE_CODE", "REGION", "LOCATION_STATE", "JOB_STATE"],
    "zip": ["ZIP", "ZIPCODE", "ZIP_CODE", "POSTAL_CODE", "POSTCODE"],
    "lat": ["LATITUDE", "LAT"],
    "lon": ["LONGITUDE", "LON", "LNG"],
    "location": ["LOCATION", "JOB_LOCATION", "LOCATION_RAW"],
}
FIRMS = {"EY (Ernst & Young)": "EY", "Deloitte": "Deloitte", "KPMG": "KPMG", "PwC": "PwC"}
STATES = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
          "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
          "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
          "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
          "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
          "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
          "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
          "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
          "pennsylvania": "PA", "puerto rico": "PR", "rhode island": "RI", "south carolina": "SC",
          "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
          "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY"}


def pick(df, key):
    upper = {c.upper(): c for c in df.columns}
    return next((upper[c] for c in COLS[key] if c in upper), None)


def load_postings() -> pd.DataFrame:
    files = sorted(SRC.glob("jobs_big4_with_roles.parquet")) or sorted(SRC.glob("jobs_big4*.parquet"))
    if not files:
        sys.exit(f"No postings in {SRC}. Run the WageScape workflow (README) and git pull first.")
    print(f"  reading {files[0].name}")
    return pd.read_parquet(files[0])


def norm_city(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.lower().str.replace(r"[^a-z ]", " ", regex=True)
    s = s.str.replace(r"\bsaint\b", "st", regex=True).str.replace(r"\bft\b", "fort", regex=True)
    return s.str.split().str.join(" ")


def norm_state(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.strip()
    return s.str.lower().map(STATES).fillna(s.str.upper().str[:2])


def classify(text: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=text.index, dtype="object")
    for line, pat in PATTERNS.items():
        hit = out.isna() & text.str.contains(pat, flags=re.I, regex=True, na=False)
        out[hit] = line
    return out


def to_cbsa(jobs: pd.DataFrame, c: dict, offices: pd.DataFrame) -> pd.Series:
    """Metro of each posting: lat/lon (with Census shapes), else ZIP, else city + state."""
    cbsa = pd.Series(pd.NA, index=jobs.index, dtype="object")
    geo = PROCESSED / "geo_cbsa.parquet"
    if c["lat"] and c["lon"] and geo.exists():
        import geopandas as gpd
        pts = gpd.GeoDataFrame(index=jobs.index, geometry=gpd.points_from_xy(
            pd.to_numeric(jobs[c["lon"]], errors="coerce"), pd.to_numeric(jobs[c["lat"]], errors="coerce")),
            crs="EPSG:4326")
        j = gpd.sjoin(pts, gpd.read_parquet(geo)[["cbsa_code", "geometry"]], predicate="within")
        cbsa.loc[j.index] = j["cbsa_code"]
    zfile = PROCESSED / "geo_zcta.parquet"
    if c["zip"] and zfile.exists():
        zmap = pd.read_parquet(zfile, columns=["zcta", "cbsa_code"]).set_index("zcta")["cbsa_code"]
        z = jobs[c["zip"]].astype(str).str.extract(r"(\d{5})")[0]
        cbsa = cbsa.fillna(z.map(zmap))
    # City + state -> metro, using the cities of the offices themselves (covers every office city)
    city, state = c["city"], c["state"]
    if not city and c["location"]:  # "Austin, TX" / "Austin, Texas, United States"
        parts = jobs[c["location"]].fillna("").astype(str).str.split(",", expand=True)
        jobs = jobs.assign(_city=parts[0], _state=parts[1] if 1 in parts else "")
        city, state = "_city", "_state"
    if city and state:
        key = norm_city(jobs[city]) + "|" + norm_state(jobs[state])
        okey = norm_city(offices["city"]) + "|" + offices["state"]
        cmap = dict(zip(okey, offices["cbsa_code"]))
        cbsa = cbsa.fillna(key.map(cmap))
    return cbsa


def main():
    jobs = load_postings()
    c = {k: pick(jobs, k) for k in COLS}
    if "--inspect" in sys.argv:
        print("Columns:", list(jobs.columns))
        print("Detected:", c)
        print(jobs[[v for v in c.values() if v]].head(10).to_string())
        return
    if not (c["company"] and c["title"]):
        sys.exit(f"Need COMPANY_STD and a title column; found {c}. Run with --inspect.")

    print(f"Coding service lines from {len(jobs):,} postings (min {MIN_POSTINGS} per firm x metro x line)")
    text = jobs[c["title"]].fillna("").astype(str)
    for k in ["family", "desc"]:
        if c[k]:
            text = text + " | " + jobs[c[k]].fillna("").astype(str).str[:600]
    jobs["line"] = classify(text)
    jobs["firm"] = jobs[c["company"]].map(FIRMS)

    path = MANUAL / "big4_offices.csv"
    offices = pd.read_csv(path, dtype=str, keep_default_na=False)
    jobs["cbsa_code"] = to_cbsa(jobs, c, offices)
    print(f"  classified: {jobs['line'].notna().mean():.0%} | placed in a metro: {jobs['cbsa_code'].notna().mean():.0%}")

    counts = (jobs.dropna(subset=["line", "cbsa_code", "firm"])
                  .groupby(["firm", "cbsa_code", "line"]).size().unstack("line", fill_value=0)
                  .reindex(columns=LINES, fill_value=0).add_prefix("postings_").reset_index())
    counts.to_csv(PROCESSED / "office_service_postings.csv", index=False)

    main_offices = offices["office_type"].ne("specialty")
    m = offices[main_offices].merge(counts, on=["firm", "cbsa_code"], how="left")
    for line in LINES:
        n = m[f"postings_{line}"].fillna(0)
        offices.loc[main_offices, line] = (n >= MIN_POSTINGS).astype(int).astype(str).values
    offices.to_csv(path, index=False)

    coded = offices[main_offices]
    print(f"  coded {len(coded)} main offices; {(~main_offices).sum()} specialty sites left blank")
    for line in LINES:
        print(f"    {line:9s} offered at {(coded[line] == '1').sum():3d} offices, not at {(coded[line] == '0').sum():3d}")
    for name, code in [("Austin", "12420"), ("New York", "35620"), ("Chicago", "16980")]:
        s = coded[coded["cbsa_code"] == code][["firm", "office_name"] + LINES]
        print(f"  {name}:\n" + s.to_string(index=False))


if __name__ == "__main__":
    main()
