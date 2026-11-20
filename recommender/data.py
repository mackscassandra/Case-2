"""Load the tables the engine needs from data/processed and data/manual."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
MANUAL = ROOT / "data" / "manual"

KEYS = {"cbsa_code": str, "zcta": str, "county_fips": str, "state_fips": str, "state": str, "zip": str}


def _parquet(name: str) -> pd.DataFrame:
    p = PROCESSED / f"{name}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{p.name} is missing. Run the ingest pipeline first "
                                f"(python ingest/run_all.py).")
    return pd.read_parquet(p)


def _manual(name: str) -> pd.DataFrame:
    return pd.read_csv(MANUAL / f"{name}.csv", dtype=KEYS)


def load_tables(include_zips: bool = True) -> dict[str, pd.DataFrame]:
    t = {
        "metro": _parquet("metro_features"),
        "offices": _parquet("offices"),
        "state_taxes": _manual("state_taxes"),
        "local_taxes": _manual("local_income_taxes"),
        "salary_base": _manual("salary_base"),
    }
    if include_zips:
        try:                      # optional: without it the app still ranks metros and offices
            t["zip"] = _parquet("zip_features")
        except FileNotFoundError:
            pass
    grid = PROCESSED / "state_income_tax.parquet"      # optional: exact state tax by salary
    if grid.exists():
        t["state_income_tax"] = pd.read_parquet(grid)
    return t
