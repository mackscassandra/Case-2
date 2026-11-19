"""Download job-listing data from Dewey month by month, keep only the Big Four
firms posted on/after 2022-01-01, and write the result to data/processed/wagescape/.

Each month's files are downloaded, filtered with DuckDB (low memory), and
deleted before the next month, so the runner's disk never fills up.

The API key is read from DEWEY_API_KEY and never written to disk or printed.
"""
import calendar
import datetime as dt
import gzip
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb

API_KEY = os.environ.get("DEWEY_API_KEY")
INCLUDE_ROLES = os.environ.get("INCLUDE_ROLES", "false").lower() == "true"
# Skip stage 1 and reuse the committed data/processed/wagescape/jobs_big4.parquet
# (saves the ~17-minute primary download when only the role table is needed).
ROLES_ONLY = os.environ.get("ROLES_ONLY", "false").lower() == "true"

# Dewey product folder IDs (not secrets)
PRIMARY_ID = "prj_cxhs7r6j__fldr_vhci9v4wjx86gg7nq"
ROLES_ID = "prj_cxhs7r6j__fldr_9ffabnvob79dxdvcn"

KEEP_FROM = dt.date(2022, 1, 1)  # "after 2021"

# Standard name -> regex (applied to lowercased COMPANY). Word boundaries keep
# "ey" from matching inside other words. Review company_name_summary.csv after
# a run to catch false positives, then tighten these patterns.
COMPANY_PATTERNS = {
    "EY (Ernst & Young)": r"\bey\b|ernst\s*(&|and)\s*young",
    "Deloitte": r"deloitte",
    "KPMG": r"\bkpmg\b",
    "PwC": r"\bpwc\b|pricewaterhouse\s*coopers",
}

WORK = Path("work")
OUT_DIR = Path("data/processed/wagescape")


def download(folder_id, dest, after=None, before=None):
    """Run the official deweypy CLI inside `dest`."""
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "deweypy", "--api-key", API_KEY,
           "speedy-download", folder_id]
    if after:
        cmd += ["--partition-key-after", after.isoformat()]
    if before:
        cmd += ["--partition-key-before", before.isoformat()]
    subprocess.run(cmd, cwd=dest, check=True, text=True, input="./dewey-downloads\n")
    return sorted(dest.rglob("*.parquet"))


def month_ranges(start, today):
    y, m = start.year, start.month
    while (y, m) <= (today.year, today.month):
        yield dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])
        m += 1
        if m == 13:
            y, m = y + 1, 1


def company_case():
    whens = "\n".join(
        f"WHEN regexp_matches(lower(COMPANY), '{pat}') THEN '{name}'"
        for name, pat in COMPANY_PATTERNS.items()
    )
    return f"CASE {whens} END"


def filter_month(con, files, out_path):
    glob_list = ", ".join(f"'{f.as_posix()}'" for f in files)
    con.execute(f"""
        COPY (
            SELECT *, {company_case()} AS COMPANY_STD
            FROM read_parquet([{glob_list}], union_by_name=true)
            WHERE CAST(POST_DATE AS DATE) >= DATE '{KEEP_FROM.isoformat()}'
              AND {company_case()} IS NOT NULL
        ) TO '{out_path.as_posix()}' (FORMAT PARQUET)
    """)
    return con.execute(f"SELECT count(*) FROM read_parquet('{out_path.as_posix()}')").fetchone()[0]


DATA_SUFFIXES = (".parquet", ".parquet.gz", ".csv", ".csv.gz")


def data_files(dest):
    """Every data file deweypy saved under `dest`, in any Dewey format. Logs what it found.

    .parquet.gz is decompressed (one file at a time, original deleted) because DuckDB
    reads gzipped CSV directly but not gzipped Parquet.
    """
    found = [p for p in dest.rglob("*") if p.is_file()]
    by_type = {}
    for p in found:
        key = next((x for x in DATA_SUFFIXES[::-1] if p.name.lower().endswith(x)), p.suffix or "(none)")
        n, b = by_type.get(key, (0, 0))
        by_type[key] = (n + 1, b + p.stat().st_size)
    print("  files found: " + (", ".join(f"{k} x{n} ({b / 1e9:.1f} GB)" for k, (n, b) in by_type.items()) or "none"),
          flush=True)
    out = []
    for p in found:
        name = p.name.lower()
        if name.endswith(".parquet.gz"):
            target = p.with_name(p.name[:-3])
            with gzip.open(p, "rb") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            p.unlink()
            out.append(target)
        elif name.endswith(DATA_SUFFIXES):
            out.append(p)
    return sorted(out)


def read_any(files):
    """DuckDB expression that reads a mix of Parquet and CSV(.gz) files by column name."""
    pq = [f for f in files if f.name.lower().endswith(".parquet")]
    csv = [f for f in files if f.name.lower().endswith((".csv", ".csv.gz"))]
    parts = []
    if pq:
        parts.append("SELECT * FROM read_parquet([" + ", ".join(f"'{f.as_posix()}'" for f in pq)
                     + "], union_by_name=true)")
    if csv:
        parts.append("SELECT * FROM read_csv([" + ", ".join(f"'{f.as_posix()}'" for f in csv)
                     + "], union_by_name=true, all_varchar=true)")
    return "(" + " UNION ALL BY NAME ".join(parts) + ")"


def metadata(folder_id):
    """Dewey's description of a table: size, file count, how it is partitioned."""
    import httpx  # installed with deweypy
    r = httpx.get(f"https://api.deweydata.io/api/v1/external/data/{folder_id}/metadata",
                  headers={"X-API-Key": API_KEY}, timeout=60)
    r.raise_for_status()
    return r.json()


def add_roles(con, final):
    """Download the Role Mapping table, keep only rows for our Big 4 JOB_IDs, and join.

    Downloads month by month when the table is date-partitioned (like stage 1), so the
    runner's disk never holds more than one month. Column names are read from the files,
    not assumed. Writes data/processed/wagescape/jobs_big4_with_roles.parquet.
    """
    meta = metadata(ROLES_ID)
    gb = (meta.get("total_size") or 0) / 1e9
    print(f"Role table: {meta.get('total_files')} files, {gb:.1f} GB, partitioned by "
          f"{meta.get('partition_column')} ({meta.get('partition_type')}, "
          f"{meta.get('partition_aggregation')}), keys {meta.get('min_partition_key')} "
          f"to {meta.get('max_partition_key')}", flush=True)

    con.execute(f"CREATE OR REPLACE TABLE big4_ids AS "
                f"SELECT DISTINCT CAST(JOB_ID AS VARCHAR) AS JOB_ID FROM read_parquet('{final.as_posix()}')")
    parts = WORK / "roleparts"
    parts.mkdir(parents=True, exist_ok=True)

    def keep_big4(files, out_path):
        # JOB_ID compared as text: the postings store it as a string, CSV may read a number.
        con.execute(f"""
            COPY (SELECT * REPLACE (CAST(JOB_ID AS VARCHAR) AS JOB_ID) FROM {read_any(files)}
                  WHERE CAST(JOB_ID AS VARCHAR) IN (SELECT JOB_ID FROM big4_ids))
            TO '{out_path.as_posix()}' (FORMAT PARQUET)
        """)
        return con.execute(f"SELECT count(*) FROM read_parquet('{out_path.as_posix()}')").fetchone()[0]

    if meta.get("partition_type") == "DATE":
        for after, before in month_ranges(KEEP_FROM, dt.date.today()):
            tag = after.strftime("%Y-%m")
            dl_dir = WORK / "roles_dl" / tag
            download(ROLES_ID, dl_dir, after, before)
            files = data_files(dl_dir)
            n = keep_big4(files, parts / f"{tag}.parquet") if files else 0
            print(f"roles {tag}: {len(files)} files -> {n} Big 4 rows", flush=True)
            shutil.rmtree(dl_dir, ignore_errors=True)
    else:
        free_gb = shutil.disk_usage(".").free / 1e9
        if gb > 0.8 * free_gb:
            sys.exit(f"Role table is {gb:.1f} GB and not split by date, but only {free_gb:.1f} GB of "
                     "disk is free on this runner. Not downloading.")
        dl_dir = WORK / "roles_dl" / "all"
        download(ROLES_ID, dl_dir)
        files = data_files(dl_dir)
        if not files:
            sys.exit("Dewey reported the download finished but no data files were saved (see 'files found').")
        n = keep_big4(files, parts / "all.parquet")
        print(f"roles (unpartitioned): {len(files)} files -> {n} Big 4 rows", flush=True)
        shutil.rmtree(dl_dir, ignore_errors=True)

    if not list(parts.glob("*.parquet")):
        sys.exit("No role-mapping parquet files were downloaded.")

    roles_src = f"read_parquet('{parts.as_posix()}/*.parquet', union_by_name=true)"
    role_cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {roles_src}").fetchall()]
    job_cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{final.as_posix()}')").fetchall()}
    print(f"Role table columns: {role_cols}", flush=True)
    if "JOB_ID" not in role_cols:
        sys.exit("Role table has no JOB_ID column; can't join it to the postings.")
    # Columns to bring over: everything the postings don't already have, plus
    # ROLE_PRIMARY (empty in the primary table, filled in the role table).
    new_cols = [c for c in role_cols if c != "JOB_ID" and (c not in job_cols or c == "ROLE_PRIMARY")]
    order = "ORDER BY MODIFY_TIMESTAMP DESC" if "MODIFY_TIMESTAMP" in role_cols else ""
    drop = " EXCLUDE (ROLE_PRIMARY)" if "ROLE_PRIMARY" in new_cols and "ROLE_PRIMARY" in job_cols else ""
    picks = ", ".join(f'r."{c}"' for c in new_cols)
    joined = OUT_DIR / "jobs_big4_with_roles.parquet"
    con.execute(f"""
        COPY (
            SELECT p.*{drop}, {picks}
            FROM read_parquet('{final.as_posix()}') p
            LEFT JOIN (
                SELECT * FROM {roles_src}
                QUALIFY row_number() OVER (PARTITION BY JOB_ID {order}) = 1
            ) r ON CAST(p.JOB_ID AS VARCHAR) = r.JOB_ID
        ) TO '{joined.as_posix()}' (FORMAT PARQUET)
    """)
    total, matched = con.execute(f"""
        SELECT count(*), count(r.JOB_ID) FROM read_parquet('{final.as_posix()}') p
        LEFT JOIN (SELECT DISTINCT JOB_ID FROM {roles_src}) r ON CAST(p.JOB_ID AS VARCHAR) = r.JOB_ID
    """).fetchone()
    print(f"Wrote {joined}: {matched:,} of {total:,} postings ({matched / max(total, 1):.0%}) "
          f"have a role; added columns {new_cols}", flush=True)


def main():
    if not API_KEY:
        sys.exit("DEWEY_API_KEY must be set.")

    shutil.rmtree(WORK, ignore_errors=True)
    parts = WORK / "parts"
    parts.mkdir(parents=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    final = OUT_DIR / "jobs_big4.parquet"
    if ROLES_ONLY:
        if not final.exists():
            sys.exit(f"ROLES_ONLY needs {final}; run once without it first.")
        print(f"ROLES_ONLY: reusing {final}", flush=True)
        add_roles(con, final)
        shutil.rmtree(WORK, ignore_errors=True)
        print("Done.")
        return

    # ---- Stage 1: primary table, one month at a time -----------------------
    total, months_with_files = 0, 0
    for after, before in month_ranges(KEEP_FROM, dt.date.today()):
        tag = after.strftime("%Y-%m")
        dl_dir = WORK / "dl" / tag
        files = download(PRIMARY_ID, dl_dir, after, before)
        if files:
            months_with_files += 1
            n = filter_month(con, files, parts / f"{tag}.parquet")
            total += n
            print(f"{tag}: {len(files)} files -> {n} matching rows", flush=True)
        else:
            print(f"{tag}: no files", flush=True)
        shutil.rmtree(dl_dir, ignore_errors=True)

    if months_with_files == 0:
        sys.exit("No parquet files were downloaded. Check the API key, folder ID, "
                 "and where deweypy saves files (run `python -m deweypy --help`).")

    # ---- Combine, keeping the latest version of each job listing -----------
    con.execute(f"""
        COPY (
            SELECT * FROM read_parquet('{parts.as_posix()}/*.parquet', union_by_name=true)
            QUALIFY row_number() OVER (PARTITION BY JOB_ID ORDER BY MODIFY_TIMESTAMP DESC) = 1
        ) TO '{final.as_posix()}' (FORMAT PARQUET)
    """)
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{final.as_posix()}')").fetchone()[0]
    print(f"Combined (deduplicated by JOB_ID): {rows} rows")

    # ---- Optional stage 2: add role classification columns -----------------
    if INCLUDE_ROLES:
        add_roles(con, final)

    # ---- Review file: which raw names matched which firm -------------------
    con.execute(f"""
        COPY (
            SELECT COMPANY_STD, COMPANY AS company_as_listed, count(*) AS listings
            FROM read_parquet('{final.as_posix()}')
            GROUP BY ALL ORDER BY COMPANY_STD, listings DESC
        ) TO '{(OUT_DIR / "company_name_summary.csv").as_posix()}' (HEADER, DELIMITER ',')
    """)

    shutil.rmtree(WORK, ignore_errors=True)
    print("Done.")


if __name__ == "__main__":
    main()
