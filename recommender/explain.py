"""Plain-English reasons behind each pick: the 3 biggest weight x score contributions."""
from __future__ import annotations

import pandas as pd


def top_reasons(row: pd.Series, weights: dict[str, float], labels: dict[str, str],
                compared_to: str, n: int = 3) -> list[str]:
    contrib = {}
    for cat, w in weights.items():
        s = row.get(f"cat_{cat}")
        if w and s is not None and pd.notna(s):
            contrib[cat] = w * s
    reasons = []
    for cat in sorted(contrib, key=contrib.get, reverse=True)[:n]:
        s = row[f"cat_{cat}"]
        flag = " (some data estimated)" if row.get(f"imputed_{cat}", False) else ""
        if s >= 99.5:
            text = f"best among {compared_to}"
        elif s <= 0.5:
            text = f"lowest among {compared_to}"
        else:
            text = f"better than {s:.0f}% of {compared_to}"
        reasons.append(f"{labels[cat]}: {text}{flag}")
    return reasons
