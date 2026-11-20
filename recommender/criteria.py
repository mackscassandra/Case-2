"""Load the criteria registry (criteria.yaml) and check it is safe to use."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

HERE = Path(__file__).parent

# Political data is display-only. Any criterion whose column looks political is refused.
_POLITICAL_HINTS = ("vote", "election", "dem_", "rep_", "gop", "party", "trump", "harris", "partisan")


@dataclass(frozen=True)
class Criterion:
    name: str
    column: str
    level: str          # "metro" or "zip"
    direction: str      # "higher" or "lower"
    category: str
    mvp: bool
    label: str


def load_criteria(path: Path | None = None) -> tuple[dict[str, str], list[Criterion]]:
    """Return (category -> display label, list of criteria)."""
    raw = yaml.safe_load((path or HERE / "criteria.yaml").read_text())
    categories = raw["categories"]
    crit = [Criterion(**c) for c in raw["criteria"]]
    for c in crit:
        if c.level not in ("metro", "zip"):
            raise ValueError(f"{c.name}: level must be metro or zip")
        if c.direction not in ("higher", "lower"):
            raise ValueError(f"{c.name}: direction must be higher or lower")
        if c.category not in categories:
            raise ValueError(f"{c.name}: unknown category {c.category!r}")
        if any(h in c.column.lower() for h in _POLITICAL_HINTS):
            raise ValueError(f"{c.name}: political data may not be scored ({c.column})")
    return categories, crit


# Columns the engine computes itself (they are not in the processed tables).
DERIVED_COLUMNS = {"metro": {"real_take_home", "income_tax_rate"}, "zip": {"miles_to_office"}}


def available_categories(crits: list[Criterion], tables: dict) -> set[str]:
    """Categories with at least one criterion whose column exists in the loaded data."""
    cols = {"metro": set(tables["metro"].columns) | DERIVED_COLUMNS["metro"],
            "zip": (set(tables["zip"].columns) if "zip" in tables else set()) | DERIVED_COLUMNS["zip"]}
    return {c.category for c in crits if c.column in cols[c.level]}
