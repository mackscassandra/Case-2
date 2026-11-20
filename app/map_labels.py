"""Hover text for the map. One tooltip template serves every layer, so each layer's rows
get the same two columns, `tip_title` and `tip_detail`, instead of layer-specific fields
(ZIP rows have no firm, office name or city, which showed up as blanks)."""
from __future__ import annotations

import pandas as pd


def office_tips(off: pd.DataFrame) -> pd.DataFrame:
    off = off.copy()
    off["tip_title"] = off["firm"].fillna("").astype(str) + " " + off["office_name"].fillna("").astype(str)
    off["tip_title"] = off["tip_title"].str.strip()
    off["tip_detail"] = off["city"].fillna("").astype(str) + ", " + off["state"].fillna("").astype(str)
    return off


def zip_tips(z: pd.DataFrame) -> pd.DataFrame:
    z = z.copy()
    z["tip_title"] = "ZIP " + z["zcta"].astype(str)
    parts = []
    if "metro" in z:
        parts.append(z["metro"].fillna("").astype(str).str.split(",").str[0] + " metro")
    if "score" in z:
        parts.append("score " + z["score"].round(0).astype("Int64").astype(str).replace("<NA>", "n/a"))
    rent = z["rent_est"] if "rent_est" in z else z["zori_latest"] if "zori_latest" in z else None
    if rent is not None:
        label = "rent $" + rent.round(0).map(lambda v: f"{v:,.0f}" if pd.notna(v) else "")
        label = label.where(rent.notna(), "rent n/a")
        if "rent_source" in z:   # flag estimates so they aren't mistaken for listings
            label = label + z["rent_source"].map(lambda s: " (est.)" if s in ("census-scaled", "metro-median") else "")
        parts.append(label)
    z["tip_detail"] = parts[0] if parts else ""
    for p in parts[1:]:
        z["tip_detail"] = z["tip_detail"] + " · " + p
    return z
