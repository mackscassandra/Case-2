"""Turn raw metrics into 0-100 percentile scores where higher is always better."""
from __future__ import annotations

import pandas as pd


def percentile_score(s: pd.Series, direction: str) -> pd.Series:
    """0-100 percentile rank. 'lower' metrics are flipped so 100 is always best.

    NaN stays NaN (imputation happens before this, in scoring.py).
    """
    s = pd.to_numeric(s, errors="coerce")
    if s.notna().sum() <= 1:
        return s.where(s.isna(), 50.0)  # nothing to compare against
    r = s.rank(pct=True, method="average")
    if direction == "lower":
        r = s.rank(pct=True, method="average", ascending=False)
    # Map so the worst value is 0 and the best is 100.
    n = s.notna().sum()
    return (r * n - 1) / (n - 1) * 100


def impute_median(df: pd.DataFrame, col: str, group: str | None = None) -> tuple[pd.Series, pd.Series]:
    """Fill gaps with the group median (then the overall median). Returns (values, was_imputed)."""
    s = pd.to_numeric(df[col], errors="coerce")
    missing = s.isna()
    if group and group in df:
        s = s.fillna(df.assign(_v=s).groupby(group)["_v"].transform("median"))
    s = s.fillna(s.median())
    return s, missing
