"""The three demo personas. Assert properties, not exact city names."""
from recommender import UserInputs, recommend
from recommender.scoring import score_metros

METRO_ARGS = ("metro", "offices", "state_taxes", "local_taxes", "salary_base")


def test_single_hiker_low_taxes(tables):
    me = UserInputs(weights={"taxes": 5, "fitness_outdoors": 5, "young_professionals": 3}, top_n_metros=3)
    m = score_metros(*(tables[k] for k in METRO_ARGS), inputs=me)
    assert set(m["state"]) <= {"TX", "WA", "FL"}          # no-income-tax states win
    assert m.iloc[0]["reasons"][0].startswith("Taxes")


def test_family_planner_gets_family_zips(tables):
    me = UserInputs(weights={"family": 5, "safety": 4, "housing": 3}, max_miles_to_office=25)
    res = recommend(tables, me)
    austin = next(r for r in res if r["metro"]["cbsa_code"] == "12420")
    top = austin["zips"].iloc[0]
    zips = tables["zip"][tables["zip"]["cbsa_code"] == "12420"]
    assert top["pct_hh_with_kids"] >= zips["pct_hh_with_kids"].median()


def test_money_maximizer_ranks_by_real_take_home(tables):
    me = UserInputs(weights={"pay": 5}, top_n_metros=6)
    m = score_metros(*(tables[k] for k in METRO_ARGS), inputs=me)
    assert list(m["cbsa_code"]) == list(m.sort_values("real_take_home", ascending=False)["cbsa_code"])


def test_every_result_explains_itself(tables):
    res = recommend(tables, UserInputs(weights={"pay": 5, "cost_of_living": 3, "walkability": 4}))
    for r in res:
        assert 1 <= len(r["metro"]["reasons"]) <= 3
        if len(r["zips"]):
            assert all(len(x) >= 1 for x in r["zips"]["reasons"])
