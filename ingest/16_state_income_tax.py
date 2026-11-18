"""State income tax by salary, for every state + DC, computed with PolicyEngine-US.

Why: state taxes have different brackets, deductions and exemptions, so one flat rate
can't describe them. This computes the actual state tax a single filer (age 25, wage
income only, standard deduction) owes at salaries from $40k to $200k in $5k steps.
The engine interpolates between steps for any salary.

Output: data/processed/state_income_tax.parquet, one row per state x salary:
  state, salary, state_income_tax, state_payroll_tax (employee SDI/PFML/etc.),
  effective_rate, tax_year, source
Also fills state_taxes.csv columns has_wage_income_tax and income_tax_rate_at_75k
(effective rate at $75k, in PERCENT), source_url and as_of.

Needs:  pip install -r requirements-tax.txt   (policyengine-us is large; only needed
to regenerate this file, not to run the app). No API key, no network calls.
Local (city/county) income taxes are NOT included here; see data/manual/local_income_taxes.csv.
"""
from __future__ import annotations

import datetime as dt
import importlib.metadata as md
import warnings

import pandas as pd

from common import MANUAL, save

warnings.filterwarnings("ignore")

TAX_YEAR = 2026
LOW, HIGH, STEPS = 40_000, 200_000, 33          # $5k steps
STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN",
          "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
          "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
          "VT", "VA", "WA", "WV", "WI", "WY"]


def grid(state: str) -> pd.DataFrame:
    from policyengine_us import Simulation

    y = TAX_YEAR
    one = {"members": ["me"]}
    situation = {
        "people": {"me": {"age": {y: 25}}},
        "tax_units": {"tu": one}, "families": {"f": one}, "spm_units": {"s": one},
        "marital_units": {"m": one}, "households": {"h": {**one, "state_code": {y: state}}},
        "axes": [[{"name": "employment_income", "count": STEPS, "min": LOW, "max": HIGH, "period": y}]],
    }
    sim = Simulation(situation=situation)
    calc = lambda v: sim.calculate(v, y)  # noqa: E731
    salary = calc("employment_income")
    federal_fica = calc("employee_social_security_tax") + calc("employee_medicare_tax")
    return pd.DataFrame({
        "state": state,
        "salary": salary.round(0),
        "state_income_tax": calc("state_income_tax").round(2),
        # Everything the employee pays in payroll tax beyond federal FICA: e.g. CA SDI,
        # NY SDI/PFL, NJ, MA and WA family-leave premiums.
        "state_payroll_tax": (calc("employee_payroll_tax") - federal_fica).round(2),
    })


def main():
    version = md.version("policyengine-us")
    print(f"State income tax grid, tax year {TAX_YEAR}, PolicyEngine-US {version}")
    frames = []
    for s in STATES:
        g = grid(s)
        frames.append(g)
        at75 = g.loc[g["salary"] == 75_000, "state_income_tax"].iloc[0]
        print(f"  {s}: ${at75:,.0f} state income tax at $75,000")
    df = pd.concat(frames, ignore_index=True)
    df["effective_rate"] = df["state_income_tax"] / df["salary"]
    df["tax_year"] = TAX_YEAR
    df["source"] = f"PolicyEngine-US {version} (single filer, wages only, standard deduction)"
    save(df, "state_income_tax")

    # Fill the summary columns in the manual state table (other columns untouched).
    st = pd.read_csv(MANUAL / "state_taxes.csv", dtype=str)
    at75 = df[df["salary"] == 75_000].set_index("state")
    st["has_wage_income_tax"] = st["state"].map(lambda s: "Y" if at75.at[s, "state_income_tax"] > 0 else "N")
    st["income_tax_rate_at_75k"] = st["state"].map(lambda s: f"{at75.at[s, 'effective_rate'] * 100:.3f}")
    st["source_url"] = f"https://github.com/PolicyEngine/policyengine-us (v{version}); computed by ingest/16_state_income_tax.py"
    st["as_of"] = dt.date.today().isoformat()
    st.to_csv(MANUAL / "state_taxes.csv", index=False)
    print(f"  updated data/manual/state_taxes.csv ({len(st)} rows)")


if __name__ == "__main__":
    main()
