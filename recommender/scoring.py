"""Scoring engine: pure functions, DataFrames in, DataFrames out. No UI, no network.

Flow: prepare metros (salary, taxes, take-home) -> hard filters -> score metros ->
rank offices in each top metro -> score ZIPs near the chosen office.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .criteria import Criterion, load_criteria
from .explain import top_reasons
from .normalize import impute_median, percentile_score
from .schemas import UserInputs
from .taxes import state_tax_from_grid, take_home

LINE_COL = {"Audit": "audit", "Tax": "tax", "Advisory": "advisory"}


# ----------------------------------------------------------------- helpers
def _rate(v) -> float:
    """Tax rate from a CSV cell, always written in PERCENT: '4.5' -> 0.045; blank -> NaN."""
    try:
        return float(v) / 100
    except (TypeError, ValueError):
        return math.nan


def local_rates_by_cbsa(local_taxes: pd.DataFrame, offices: pd.DataFrame) -> pd.Series:
    """Resident local income tax rate (decimal) per cbsa_code.

    Rows with a blank cbsa_code are matched to a metro through the office list (same
    city + state). Assumes the user lives in the city where the office is.
    """
    if local_taxes is None or local_taxes.empty:
        return pd.Series(dtype=float)
    lt = local_taxes.copy()
    lt["r"] = lt["resident_rate"].map(_rate)
    if "cbsa_code" not in lt:
        lt["cbsa_code"] = np.nan
    city_cbsa = (offices.dropna(subset=["cbsa_code"])
                 .assign(k=lambda d: d["city"].str.lower().str.strip() + "|" + d["state"].str.upper())
                 .groupby("k")["cbsa_code"].agg(lambda s: s.mode().iloc[0])) if "city" in offices else pd.Series(dtype=str)
    keys = lt["city"].astype(str).str.lower().str.strip() + "|" + lt["state"].astype(str).str.upper()
    lt["cbsa_code"] = lt["cbsa_code"].where(lt["cbsa_code"].notna() & lt["cbsa_code"].astype(str).str.strip().ne(""),
                                            keys.map(city_cbsa))
    return lt.dropna(subset=["cbsa_code"]).groupby("cbsa_code")["r"].max()


def principal_state(cbsa_name: str) -> str | None:
    """'New York-Newark-Jersey City, NY-NJ' -> 'NY' (first-listed state)."""
    if not isinstance(cbsa_name, str) or "," not in cbsa_name:
        return None
    return cbsa_name.rsplit(",", 1)[1].strip().split("-")[0][:2]


def miles_between(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * np.arcsin(np.sqrt(a))


def offers_line(offices: pd.DataFrame, line: str) -> pd.Series:
    """True = offers it, False = says it doesn't, NaN = unknown (column blank)."""
    col = LINE_COL[line]
    if col not in offices:
        return pd.Series(np.nan, index=offices.index)
    v = offices[col].astype("string").str.strip().str.upper()
    # Accept Y/N (hand-entered) and 1/0 (written by ingest/15_office_service_lines.py).
    return v.map({"Y": True, "1": True, "1.0": True, "N": False, "0": False, "0.0": False}).astype("object")


def base_salary(inputs: UserInputs, salary_base: pd.DataFrame, firm: str | None = None) -> float:
    if inputs.salary is not None:
        return float(inputs.salary)
    sb = salary_base[salary_base["service_line"].str.lower() == inputs.service_line.lower()]
    if firm is not None:
        sb_f = sb[sb["firm"] == firm]
        sb = sb_f if len(sb_f) else sb
    mids = (pd.to_numeric(sb["salary_low"], errors="coerce") + pd.to_numeric(sb["salary_high"], errors="coerce")) / 2
    if mids.notna().sum() == 0:
        raise ValueError(f"No salary for {inputs.service_line}: enter a salary or fill data/manual/salary_base.csv")
    return float(mids.median())


# ----------------------------------------------------------------- metros
def prepare_metros(metro: pd.DataFrame, offices: pd.DataFrame, state_taxes: pd.DataFrame,
                   local_taxes: pd.DataFrame, salary_base: pd.DataFrame, inputs: UserInputs,
                   state_grid: pd.DataFrame | None = None) -> pd.DataFrame:
    """Keep metros with an eligible office; add state, taxes, salary and real take-home.

    state_grid (data/processed/state_income_tax.parquet) gives exact state tax at each
    salary; without it the flat income_tax_rate_at_75k from state_taxes.csv is used.
    """
    off = offices[offices["firm"].isin(inputs.firms)].copy()
    off = off[offers_line(off, inputs.service_line).ne(False)]          # drop explicit "N" only
    m = metro[metro["cbsa_code"].isin(off["cbsa_code"].dropna().unique())].copy()

    m["state"] = m["cbsa_name"].map(principal_state)
    st = state_taxes.set_index("state")
    m["has_state_income_tax"] = m["state"].map(st["has_wage_income_tax"]).str.upper().eq("Y")
    m["state_rate"] = [0.0 if s in st.index and str(st.at[s, "has_wage_income_tax"]).upper() == "N"
                       else _rate(st.at[s, "income_tax_rate_at_75k"]) if s in st.index else math.nan
                       for s in m["state"]]
    m["local_rate"] = m["cbsa_code"].map(local_rates_by_cbsa(local_taxes, offices)).fillna(0.0)

    base = base_salary(inputs, salary_base)
    mult = m["wage_multiplier"] if "wage_multiplier" in m else pd.Series(np.nan, index=m.index)
    m["salary_estimated_multiplier"] = mult.isna()
    m["salary"] = base * mult.fillna(1.0)
    rpp = m["rpp_all"] if "rpp_all" in m else pd.Series(np.nan, index=m.index)

    th = []
    for s, state, rate, local, p in zip(m["salary"], m["state"], m["state_rate"], m["local_rate"], rpp):
        if state_grid is not None and len(state_grid):
            st_tax, st_payroll = state_tax_from_grid(state_grid, state, s)
            th.append(take_home(s, local_rate=local, rpp=p, state_tax=st_tax, state_payroll_tax=st_payroll))
        else:
            th.append(take_home(s, state_rate=rate, local_rate=local, rpp=p))
    for k in ("federal_tax", "fica", "state_tax", "state_payroll_tax", "local_tax", "net", "real_take_home"):
        m[k] = [t[k] for t in th]
    m["state_tax_method"] = "exact (PolicyEngine grid)" if state_grid is not None and len(state_grid) else "flat rate at $75k"
    # Rate used for the "Taxes" score: everything state + local takes, as a share of salary.
    m["income_tax_rate"] = (m["state_tax"] + m["state_payroll_tax"] + m["local_tax"]) / m["salary"]
    m["n_offices"] = m["cbsa_code"].map(off.groupby("cbsa_code").size())
    return m


def filter_metros(m: pd.DataFrame, inputs: UserInputs) -> pd.DataFrame:
    keep = pd.Series(True, index=m.index)
    if inputs.no_state_income_tax:
        keep &= ~m["has_state_income_tax"].fillna(True)
    if inputs.exclude_states:
        keep &= ~m["state"].isin(inputs.exclude_states)
    return m[keep]


# ----------------------------------------------------------------- generic scorer
def score_table(df: pd.DataFrame, level: str, inputs: UserInputs, group: str | None = None) -> pd.DataFrame:
    """Add cat_<category> (0-100), imputed_<category>, score, reasons and skipped categories."""
    labels, crits = load_criteria()
    crits = [c for c in crits if c.level == level and c.column in df.columns]
    out = df.copy()
    by_cat: dict[str, list[Criterion]] = {}
    for c in crits:
        by_cat.setdefault(c.category, []).append(c)

    for cat, cs in by_cat.items():
        scores, imputed = [], pd.Series(False, index=out.index)
        for c in cs:
            vals, miss = impute_median(out, c.column, group)
            if vals.isna().all():
                continue
            scores.append(percentile_score(vals, c.direction))
            imputed |= miss
        if scores:
            out[f"cat_{cat}"] = pd.concat(scores, axis=1).mean(axis=1)
            out[f"imputed_{cat}"] = imputed

    weights = {k: v for k, v in inputs.weights.items() if v and k in by_cat}
    wanted_here = {k for k, v in inputs.weights.items() if v and k in labels and
                   any(c.category == k and c.level == level for c in load_criteria()[1])}
    skipped = sorted(wanted_here - {k for k in weights if f"cat_{k}" in out})
    used = {k: v for k, v in weights.items() if f"cat_{k}" in out}
    if used:
        num = sum(out[f"cat_{k}"] * w for k, w in used.items())
        out["score"] = num / sum(used.values())
    else:
        out["score"] = 50.0
    out["low_confidence"] = (pd.concat([out[f"imputed_{k}"] for k in used], axis=1).any(axis=1)
                             if used else False)
    noun = "Big 4 metros" if level == "metro" else "ZIPs in this metro"
    out["reasons"] = [top_reasons(r, used, labels, noun) for _, r in out.iterrows()]
    out["skipped_categories"] = [skipped] * len(out)   # wanted but no data yet -> shown, never silent
    return out.sort_values("score", ascending=False)


# ----------------------------------------------------------------- public API
def score_metros(metro, offices, state_taxes, local_taxes, salary_base, inputs: UserInputs,
                 state_grid: pd.DataFrame | None = None) -> pd.DataFrame:
    m = filter_metros(prepare_metros(metro, offices, state_taxes, local_taxes, salary_base, inputs,
                                     state_grid), inputs)
    if m.empty:
        return m
    return score_table(m, "metro", inputs).head(inputs.top_n_metros)


def rank_offices(offices, cbsa_code: str, metro_row: pd.Series, salary_base, inputs: UserInputs) -> pd.DataFrame:
    off = offices[(offices["cbsa_code"] == cbsa_code) & offices["firm"].isin(inputs.firms)].copy()
    off["offers_line"] = offers_line(off, inputs.service_line)
    off = off[off["offers_line"].ne(False)]
    mult = metro_row.get("wage_multiplier", np.nan)
    mult = 1.0 if pd.isna(mult) else mult
    off["salary_est"] = [base_salary(inputs, salary_base, f) * mult for f in off["firm"]]
    off["service_line_confirmed"] = off["offers_line"].eq(True)
    return off.sort_values(["service_line_confirmed", "salary_est", "firm"], ascending=[False, False, True])


def score_zips(zips: pd.DataFrame, cbsa_code: str, office_lat: float, office_lon: float,
               inputs: UserInputs) -> pd.DataFrame:
    z = zips[zips["cbsa_code"] == cbsa_code].copy()
    z["miles_to_office"] = miles_between(z["lat"], z["lon"], office_lat, office_lon)
    if inputs.max_miles_to_office is not None:
        z = z[z["miles_to_office"] <= inputs.max_miles_to_office]
    if inputs.max_rent is not None and "zori_latest" in z:
        z = z[z["zori_latest"].isna() | (z["zori_latest"] <= inputs.max_rent)]
    if inputs.min_walk_index is not None and "walk_index" in z:
        z = z[z["walk_index"].isna() | (z["walk_index"] >= inputs.min_walk_index)]
    if z.empty:
        return z
    return score_table(z, "zip", inputs).head(inputs.top_n_zips)


def recommend(tables: dict[str, pd.DataFrame], inputs: UserInputs) -> list[dict]:
    """End-to-end: top metros, each with ranked offices and top ZIPs near the best office."""
    metros = score_metros(tables["metro"], tables["offices"], tables["state_taxes"],
                          tables["local_taxes"], tables["salary_base"], inputs,
                          tables.get("state_income_tax"))
    results = []
    for _, row in metros.iterrows():
        offs = rank_offices(tables["offices"], row["cbsa_code"], row, tables["salary_base"], inputs)
        zips = pd.DataFrame()
        if len(offs) and "zip" in tables:
            o = offs.iloc[0]
            zips = score_zips(tables["zip"], row["cbsa_code"], float(o["lat"]), float(o["lon"]), inputs)
        results.append({"metro": row, "offices": offs, "zips": zips})
    return results
