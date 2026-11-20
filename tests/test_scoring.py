import numpy as np
import pandas as pd
import pytest

from recommender.criteria import Criterion, load_criteria
from recommender.normalize import percentile_score
from recommender.schemas import UserInputs
from recommender.scoring import principal_state, rank_offices, score_metros, score_zips


def test_percentile_direction():
    s = pd.Series([1, 2, 3])
    assert list(percentile_score(s, "higher")) == [0, 50, 100]
    assert list(percentile_score(s, "lower")) == [100, 50, 0]


def test_principal_state():
    assert principal_state("New York-Newark-Jersey City, NY-NJ") == "NY"
    assert principal_state("Austin-Round Rock-San Marcos, TX") == "TX"


def test_criteria_registry_loads_and_has_no_politics():
    cats, crits = load_criteria()
    assert crits and all(c.category in cats for c in crits)
    for c in crits:
        assert "vote" not in c.column and "election" not in c.column


def test_political_column_is_refused(tmp_path):
    bad = tmp_path / "c.yaml"
    bad.write_text("categories: {x: X}\ncriteria:\n  - {name: v, column: dem_vote_share, level: metro, "
                   "direction: higher, category: x, mvp: true, label: v}\n")
    with pytest.raises(ValueError, match="political"):
        load_criteria(bad)


def test_no_state_income_tax_filter(tables):
    m = score_metros(**{k: tables[k] for k in ("metro", "offices", "state_taxes", "local_taxes", "salary_base")},
                     inputs=UserInputs(no_state_income_tax=True, weights={"pay": 5}))
    assert set(m["state"]) <= {"TX", "WA", "FL"}


def test_missing_data_is_imputed_and_flagged(tables):
    tables["metro"].loc[0, "rpp_all"] = np.nan          # Austin: unknown price level
    m = score_metros(**{k: tables[k] for k in ("metro", "offices", "state_taxes", "local_taxes", "salary_base")},
                     inputs=UserInputs(weights={"cost_of_living": 5}, top_n_metros=10))
    austin = m.set_index("cbsa_code").loc["12420"]
    assert austin["imputed_cost_of_living"] and austin["low_confidence"]
    assert len(m) == 6                                    # nothing silently dropped


def test_wanted_category_without_data_is_reported(tables):
    tables["metro"] = tables["metro"].drop(columns=["violent_per_100k", "property_per_100k"])  # no crime data yet
    m = score_metros(**{k: tables[k] for k in ("metro", "offices", "state_taxes", "local_taxes", "salary_base")},
                     inputs=UserInputs(weights={"pay": 3, "safety": 5}, top_n_metros=10))
    assert m.iloc[0]["skipped_categories"] == ["safety"]   # shown to the user, never silent


def test_office_marked_N_for_service_line_is_excluded(tables):
    metro_row = tables["metro"].iloc[0]
    offs = rank_offices(tables["offices"], "12420", metro_row, tables["salary_base"], UserInputs(service_line="Audit"))
    assert list(offs["firm"]) == ["Deloitte"]           # Austin KPMG says audit = N


def test_blank_service_line_is_kept_but_unconfirmed(tables):
    metro_row = tables["metro"].iloc[1]
    offs = rank_offices(tables["offices"], "35620", metro_row, tables["salary_base"], UserInputs(service_line="Tax", salary=80000))
    assert len(offs) == 1 and not offs.iloc[0]["service_line_confirmed"]


def test_commute_filter(tables):
    z = score_zips(tables["zip"], "12420", 30.27, -97.74, UserInputs(max_miles_to_office=10, weights={"housing": 5}))
    assert "78613" not in set(z["zcta"])                 # ~17 miles from downtown Austin
    assert (z["miles_to_office"] <= 10).all()


def test_salary_required_when_no_base(tables):
    empty = tables["salary_base"].iloc[0:0]
    with pytest.raises(ValueError, match="enter a salary"):
        score_metros(tables["metro"], tables["offices"], tables["state_taxes"], tables["local_taxes"], empty,
                     UserInputs(weights={"pay": 5}))


def test_local_tax_matched_to_metro_by_office_city(tables):
    from recommender.scoring import prepare_metros
    m = prepare_metros(tables["metro"], tables["offices"], tables["state_taxes"], tables["local_taxes"],
                       tables["salary_base"], UserInputs()).set_index("cbsa_code")
    assert m.at["35620", "local_rate"] == pytest.approx(0.03)     # NYC row had no cbsa_code
    assert m.at["12420", "local_rate"] == 0


def test_exact_state_grid_is_used_when_available(tables):
    from recommender.scoring import prepare_metros
    grid = pd.DataFrame({"state": ["TX", "TX"], "salary": [40000, 200000],
                         "state_income_tax": [0, 0], "state_payroll_tax": [0, 0]})
    m = prepare_metros(tables["metro"], tables["offices"], tables["state_taxes"], tables["local_taxes"],
                       tables["salary_base"], UserInputs(), state_grid=grid).set_index("cbsa_code")
    assert m.at["12420", "state_tax_method"].startswith("exact")
    assert m.at["12420", "state_tax"] == 0


def test_service_line_accepts_1_0_from_ingest_15(tables):
    from recommender.scoring import offers_line
    off = pd.DataFrame({"audit": ["1", "0", "", "Y", "N", "1.0"]})
    got = [None if pd.isna(x) else x for x in offers_line(off, "Audit")]
    assert got == [True, False, None, True, False, True]


def test_available_categories_follow_the_loaded_data(tables):
    from recommender.criteria import available_categories, load_criteria
    _, crits = load_criteria()
    have = available_categories(crits, tables)
    assert {"pay", "cost_of_living", "safety"} <= have          # metro columns + derived pay
    no_zip = {k: v for k, v in tables.items() if k != "zip"}
    assert "walkability" in have and "walkability" not in available_categories(crits, no_zip)
    assert "pay" in available_categories(crits, no_zip)          # metro-level still works


def test_recommend_works_without_zip_table(tables):
    from recommender import UserInputs, recommend
    no_zip = {k: v for k, v in tables.items() if k != "zip"}
    res = recommend(no_zip, UserInputs(salary=80000, weights={"pay": 5, "safety": 3}))
    assert res and all(r["zips"].empty for r in res)


def test_load_tables_without_zip_file(tmp_path, monkeypatch):
    import shutil
    from recommender import data
    proc = tmp_path / "processed"; proc.mkdir()
    for f in ("metro_features.parquet", "offices.parquet"):
        shutil.copy(data.PROCESSED / f, proc / f)
    monkeypatch.setattr(data, "PROCESSED", proc)
    t = data.load_tables()
    assert "metro" in t and "zip" not in t
