import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.map_labels import office_tips, zip_tips  # noqa: E402


def test_office_tip():
    o = pd.DataFrame({"firm": ["Deloitte"], "office_name": ["Austin"], "city": ["Austin"], "state": ["TX"]})
    t = office_tips(o).iloc[0]
    assert t.tip_title == "Deloitte Austin" and t.tip_detail == "Austin, TX"


def test_zip_tip_has_its_own_fields_and_flags_estimates():
    z = pd.DataFrame({"zcta": ["78704", "78701", "78702"], "metro": ["Austin-Round Rock, TX"] * 3,
                      "score": [82.4, 70.0, 55.0], "rent_est": [1650.0, 1800.0, np.nan],
                      "rent_source": ["zillow", "census-scaled", None]})
    t = zip_tips(z)
    assert t.tip_title.tolist() == ["ZIP 78704", "ZIP 78701", "ZIP 78702"]
    assert t.tip_detail[0] == "Austin-Round Rock metro · score 82 · rent $1,650"
    assert t.tip_detail[1].endswith("rent $1,800 (est.)")
    assert t.tip_detail[2].endswith("rent n/a")


def test_zip_tip_without_rent_or_score_columns():
    t = zip_tips(pd.DataFrame({"zcta": ["78704"]}))
    assert t.tip_title[0] == "ZIP 78704" and t.tip_detail[0] == ""
