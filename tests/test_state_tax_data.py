"""Checks on the real data/processed/state_income_tax.parquet (skipped if not built)."""
from pathlib import Path

import pandas as pd
import pytest

GRID = Path(__file__).resolve().parents[1] / "data" / "processed" / "state_income_tax.parquet"
pytestmark = pytest.mark.skipif(not GRID.exists(), reason="run ingest/16_state_income_tax.py first")


@pytest.fixture(scope="module")
def at75():
    g = pd.read_parquet(GRID)
    return g[g["salary"] == 75000].set_index("state")


def test_all_states_and_dc(at75):
    assert len(at75) == 51


def test_no_wage_tax_states_are_zero(at75):
    for s in ["AK", "FL", "NV", "NH", "SD", "TN", "TX", "WA", "WY"]:
        assert at75.at[s, "state_income_tax"] == 0


def test_flat_tax_states_match_published_structure(at75):
    assert at75.at["PA", "state_income_tax"] == pytest.approx(75000 * 0.0307, abs=1)            # 3.07%, no deduction
    assert at75.at["IN", "state_income_tax"] == pytest.approx((75000 - 1000) * 0.0295, abs=1)   # 2.95%, $1,000 exemption
    assert at75.at["CO", "state_income_tax"] == pytest.approx((75000 - 16100) * 0.044, abs=1)   # 4.4% of federal taxable
    assert at75.at["GA", "state_income_tax"] == pytest.approx((75000 - 15000) * 0.0499, abs=1)  # 4.99%, $15k deduction (2026)
