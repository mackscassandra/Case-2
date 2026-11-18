"""After-tax, cost-of-living-adjusted ("real") take-home pay.

Federal tax and FICA follow config/tax_params_<year>.yaml exactly (single filer,
standard deduction). State and local income tax use one effective rate per place,
read from data/manual/state_taxes.csv (income_tax_rate_at_75k) and
data/manual/local_income_taxes.csv (resident_rate). Those are approximations:
a single effective rate is applied to every salary.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG = Path(__file__).parent / "config"


@lru_cache
def load_tax_params(year: int = 2026) -> dict:
    path = CONFIG / f"tax_params_{year}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No federal tax parameters for {year}: add {path.name} (see tax_params_2026.yaml).")
    return yaml.safe_load(path.read_text())


def federal_income_tax(salary: float, params: dict) -> float:
    taxable = max(0.0, salary - params["standard_deduction"])
    brackets = params["brackets"]
    tax = 0.0
    for i, b in enumerate(brackets):
        top = brackets[i + 1]["over"] if i + 1 < len(brackets) else math.inf
        if taxable > b["over"]:
            tax += (min(taxable, top) - b["over"]) * b["rate"]
    return tax


def fica(salary: float, params: dict) -> float:
    ss = min(salary, params["social_security_wage_base"]) * params["social_security_rate"]
    medicare = salary * params["medicare_rate"]
    extra = max(0.0, salary - params["additional_medicare_threshold_single"]) * params["additional_medicare_rate"]
    return ss + medicare + extra


def take_home(salary: float, state_rate: float, local_rate: float = 0.0,
              rpp: float | None = 100.0, year: int = 2026) -> dict:
    """Return each piece so the app can show the math.

    state_rate / local_rate are effective rates as decimals (0.045 = 4.5%).
    NaN state_rate (unknown) gives NaN take-home rather than a guess.
    rpp is the BEA Regional Price Parity (US = 100).
    """
    p = load_tax_params(year)
    fed = federal_income_tax(salary, p)
    fic = fica(salary, p)
    state = salary * state_rate
    local = salary * (local_rate or 0.0)
    net = salary - fed - fic - state - local
    real = net / (rpp / 100) if rpp and not math.isnan(rpp) else math.nan
    return {"gross": salary, "federal_tax": fed, "fica": fic, "state_tax": state,
            "local_tax": local, "net": net, "rpp": rpp, "real_take_home": real,
            "tax_year": p["tax_year"]}
