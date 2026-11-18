"""After-tax, cost-of-living-adjusted ("real") take-home pay.

Federal tax and FICA follow config/tax_params_<year>.yaml exactly (single filer,
standard deduction).

State tax, best to fallback:
  1. data/processed/state_income_tax.parquet (ingest/16): actual state income tax and
     state payroll tax at each salary, interpolated. Exact for single filers with wages.
  2. data/manual/state_taxes.csv income_tax_rate_at_75k: one effective rate (percent)
     applied to every salary. Approximate.
Local tax: data/manual/local_income_taxes.csv resident_rate (percent), applied as a flat
rate to wages.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
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


def state_tax_from_grid(grid: pd.DataFrame, state: str, salary: float) -> tuple[float, float]:
    """(state income tax, state payroll tax) at `salary`, interpolated from the ingest/16 grid.

    Above the grid's top salary, the top effective rate is applied. Unknown state -> NaN.
    """
    g = grid[grid["state"] == state].sort_values("salary")
    if g.empty:
        return math.nan, math.nan
    x = g["salary"].to_numpy()
    if salary > x[-1]:
        top = g.iloc[-1]
        return (salary * top["state_income_tax"] / top["salary"],
                salary * top["state_payroll_tax"] / top["salary"])
    return (float(np.interp(salary, x, g["state_income_tax"])),
            float(np.interp(salary, x, g["state_payroll_tax"])))


def take_home(salary: float, state_rate: float = math.nan, local_rate: float = 0.0,
              rpp: float | None = 100.0, year: int = 2026,
              state_tax: float | None = None, state_payroll_tax: float = 0.0) -> dict:
    """Return each piece so the app can show the math.

    Pass `state_tax` (dollars, e.g. from state_tax_from_grid) when known; otherwise
    `state_rate` (decimal, 0.045 = 4.5%) is applied to the salary.
    NaN state tax (unknown) gives NaN take-home rather than a guess.
    rpp is the BEA Regional Price Parity (US = 100).
    """
    p = load_tax_params(year)
    fed = federal_income_tax(salary, p)
    fic = fica(salary, p)
    state = state_tax if state_tax is not None else salary * state_rate
    local = salary * (local_rate or 0.0)
    net = salary - fed - fic - state - (state_payroll_tax or 0.0) - local
    real = net / (rpp / 100) if rpp and not math.isnan(rpp) else math.nan
    return {"gross": salary, "federal_tax": fed, "fica": fic, "state_tax": state,
            "state_payroll_tax": state_payroll_tax or 0.0, "local_tax": local, "net": net,
            "rpp": rpp, "real_take_home": real, "tax_year": p["tax_year"]}
