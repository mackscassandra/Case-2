"""WageScape job postings (Dewey) -> Big 4 associate pay by firm x service line x metro.

Run ONE step at a time, in order, and look at the output before the next step:

  python ingest/13_dewey_wagescape.py meta       # date range, partitions (downloads nothing)
  python ingest/13_dewey_wagescape.py sample     # first 200 rows -> learn real column names
  python ingest/13_dewey_wagescape.py list       # how many files / GB for the date window
  python ingest/13_dewey_wagescape.py download   # download only that window
  python ingest/13_dewey_wagescape.py filter     # keep Big 4 associate postings, summarize pay

Setup (once):
  pip install "deweydatapy@git+https://github.com/Dewey-Data/deweydatapy" duckdb
  In .env (never commit it):
    DEWEY_API_KEY=...            # Dewey -> Connections -> Add Connection
    DEWEY_WAGESCAPE_PATH=...     # WageScape page -> Get / Connect to API -> copy the API endpoint
  Add this line to .gitignore:   data/licensed/

Licensed data: everything stays in data/licensed/ (git-ignored). Nothing here writes to
data/processed/ until the instructor confirms aggregates may be shared.
"""
from __future__ import annotations

import sys
from pathlib import Path

from common import ROOT, api_key

# ---- Settings you may change -------------------------------------------------
# Keep the window SHORT. One quarter is plenty for a salary snapshot.
START_DATE = "2025-07-01"
END_DATE = "2025-09-30"
MAX_DOWNLOAD_GB = 5          # 'download' refuses to run above this; raise it on purpose only

# Fill these in AFTER running `sample` and reading the data dictionary.
# Left side = what this script calls it; right side = WageScape's real column name.
COLS = {
    "employer": None,        # e.g. company / employer name column
    "title": None,           # job title column
    "city": None,
    "state": None,
    "salary_min": None,
    "salary_max": None,
    "pay_period": None,      # annual / hourly, if the dataset has it; leave None if not
    "posted_date": None,
}
# ------------------------------------------------------------------------------

OUT = ROOT / "data" / "licensed" / "wagescape"
RAW = OUT / "raw"


def creds():
    import deweydatapy as ddp
    return ddp, api_key("DEWEY_API_KEY"), api_key("DEWEY_WAGESCAPE_PATH")


def step_meta():
    ddp, key, path = creds()
    ddp.get_meta(key, path, print_meta=True)
    print("\nCheck: is there a date partition? What are the min/max dates?"
          "\nIf the window above is outside that range, edit START_DATE/END_DATE.")


def step_sample():
    ddp, key, path = creds()
    df = ddp.read_sample0(key, path, nrows=200)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "sample_200.csv", index=False)
    print(df.dtypes.to_string())
    print(f"\nSaved {OUT / 'sample_200.csv'}. Open it, then fill in COLS at the top of this script.")


def step_list():
    ddp, key, path = creds()
    files = ddp.get_file_list(key, path, start_date=START_DATE, end_date=END_DATE, print_info=True)
    size_col = next((c for c in files.columns if "size" in c.lower()), None)
    gb = files[size_col].sum() / 1e9 if size_col else float("nan")
    print(f"\n{len(files)} files, about {gb:.2f} GB for {START_DATE} to {END_DATE}.")
    return files, gb


def step_download():
    ddp, _, _ = creds()
    files, gb = step_list()
    if gb == gb and gb > MAX_DOWNLOAD_GB:  # gb == gb is False for NaN
        sys.exit(f"Stopping: {gb:.1f} GB > MAX_DOWNLOAD_GB={MAX_DOWNLOAD_GB}. Shorten the window.")
    RAW.mkdir(parents=True, exist_ok=True)
    ddp.download_files(files, str(RAW), filename_prefix="wagescape_", skip_exists=True)
    print(f"Downloaded to {RAW}")


def step_filter():
    import duckdb

    missing = [k for k, v in COLS.items() if v is None and k not in ("pay_period", "posted_date")]
    if missing:
        sys.exit(f"Fill in COLS first (missing: {missing}). Run the 'sample' step to see column names.")

    files = sorted(RAW.glob("*.parquet")) or sorted(RAW.glob("*.csv*"))
    if not files:
        sys.exit(f"No files in {RAW}. Run 'download' first.")
    reader = "read_parquet" if files[0].suffix == ".parquet" else "read_csv_auto"
    src = f"{reader}('{RAW.as_posix()}/*{files[0].suffix if reader == 'read_parquet' else '.csv*'}')"

    c = COLS
    period = f", {c['pay_period']} AS pay_period" if c["pay_period"] else ", NULL AS pay_period"
    postings = duckdb.sql(f"""
        SELECT
          CASE
            WHEN regexp_matches(lower({c['employer']}), 'deloitte') THEN 'Deloitte'
            WHEN regexp_matches(lower({c['employer']}), 'pwc|pricewaterhouse') THEN 'PwC'
            WHEN regexp_matches(lower({c['employer']}), 'ernst|^ey$|^ey ') THEN 'EY'
            WHEN regexp_matches(lower({c['employer']}), 'kpmg') THEN 'KPMG'
          END AS firm,
          CASE
            WHEN regexp_matches(lower({c['title']}), 'audit|assurance') THEN 'Audit'
            WHEN regexp_matches(lower({c['title']}), 'tax') THEN 'Tax'
            WHEN regexp_matches(lower({c['title']}), 'advisory|consult|risk') THEN 'Advisory'
          END AS service_line,
          {c['title']} AS title, {c['city']} AS city, {c['state']} AS state,
          TRY_CAST({c['salary_min']} AS DOUBLE) AS salary_min,
          TRY_CAST({c['salary_max']} AS DOUBLE) AS salary_max
          {period}
        FROM {src}
        WHERE regexp_matches(lower({c['employer']}), 'deloitte|pwc|pricewaterhouse|ernst|^ey$|^ey |kpmg')
          AND regexp_matches(lower({c['title']}), 'associate|staff|assistant')
          AND NOT regexp_matches(lower({c['title']}), 'senior|manager|director|partner|intern')
          AND {c['salary_min']} IS NOT NULL
    """).df()
    postings = postings.dropna(subset=["firm", "service_line"])

    # Sanity: hourly pay or junk values would distort medians. Flag rather than guess.
    odd = postings[(postings["salary_min"] < 30000) | (postings["salary_max"] > 200000)]
    print(f"{len(postings):,} Big 4 associate postings with pay; {len(odd):,} look hourly/out of range "
          "(excluded below; check pay_period).")
    postings = postings.drop(odd.index)

    summary = (postings.groupby(["firm", "service_line", "state", "city"])
               .agg(n_postings=("salary_min", "size"),
                    salary_low=("salary_min", "median"),
                    salary_high=("salary_max", "median"))
               .reset_index().sort_values("n_postings", ascending=False))
    summary["source"] = "WageScape via Dewey (licensed)"
    summary["window"] = f"{START_DATE} to {END_DATE}"

    postings.to_parquet(OUT / "big4_associate_postings.parquet", index=False)
    summary.to_csv(OUT / "big4_salary_summary.csv", index=False)
    print(summary.head(25).to_string(index=False))
    print(f"\nSaved {OUT / 'big4_salary_summary.csv'} ({len(summary)} rows). "
          "Review it, then copy firm x service-line ranges into data/manual/salary_base.csv.")


STEPS = {"meta": step_meta, "sample": step_sample, "list": step_list,
         "download": step_download, "filter": step_filter}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STEPS:
        sys.exit(__doc__)
    STEPS[sys.argv[1]]()
