import pytest

from recommender.taxes import federal_income_tax, fica, load_tax_params, take_home

P = load_tax_params(2026)


def test_federal_tax_75k_single_2026():
    # taxable = 75,000 - 16,100 = 58,900
    # 10% x 12,400 + 12% x (50,400-12,400) + 22% x (58,900-50,400) = 1,240 + 4,560 + 1,870
    assert federal_income_tax(75000, P) == pytest.approx(7670.0)


def test_no_tax_below_standard_deduction():
    assert federal_income_tax(16000, P) == 0


def test_fica_below_and_above_wage_base():
    assert fica(75000, P) == pytest.approx(75000 * 0.0765)
    # Above the SS wage base and the additional-Medicare threshold
    expected = 184500 * 0.062 + 250000 * 0.0145 + 50000 * 0.009
    assert fica(250000, P) == pytest.approx(expected)


def test_real_take_home_no_income_tax_state():
    t = take_home(75000, state_rate=0.0, rpp=115)
    net = 75000 - 7670 - 75000 * 0.0765
    assert t["net"] == pytest.approx(net)
    assert t["real_take_home"] == pytest.approx(net / 1.15)


def test_rpp_adjustment_matches_plan_example():
    # Build plan: $75,000 at RPP 115 ~= $65,200 in national dollars before taxes
    assert 75000 / 1.15 == pytest.approx(65217, abs=1)


def test_unknown_state_rate_gives_nan_not_a_guess():
    import math
    assert math.isnan(take_home(75000, state_rate=float("nan"), rpp=100)["net"])
