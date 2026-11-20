"""rent_est: Zillow where present, else Census scaled to Zillow's level, else metro median."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
from build_tables import MIN_ZIPS_FOR_METRO_RATIO, add_rent_estimate  # noqa: E402


def _zips():
    # Metro A: 5 ZIPs with both sources, Zillow = 1.5 x Census. Plus a Census-only ZIP,
    # a ZIP with neither, and a Zillow-only ZIP. Metro B: only 1 ZIP with both (too few).
    a = pd.DataFrame({"zcta": [f"A{i}" for i in range(5)], "cbsa_code": "A",
                      "median_gross_rent": [1000.0] * 5, "zori_latest": [1500.0] * 5})
    extra = pd.DataFrame({"zcta": ["A_census", "A_none", "A_zillow"], "cbsa_code": "A",
                          "median_gross_rent": [800.0, np.nan, np.nan],
                          "zori_latest": [np.nan, np.nan, 2000.0]})
    b = pd.DataFrame({"zcta": ["B_both", "B_census"], "cbsa_code": "B",
                      "median_gross_rent": [1000.0, 1000.0], "zori_latest": [1200.0, np.nan]})
    return pd.concat([a, extra, b], ignore_index=True).set_index("zcta", drop=False)


def test_zillow_is_kept_as_is():
    z = add_rent_estimate(_zips())
    assert z.loc["A0", "rent_est"] == 1500 and z.loc["A0", "rent_source"] == "zillow"
    assert z.loc["A_zillow", "rent_est"] == 2000


def test_census_only_zip_is_scaled_by_its_metro_ratio():
    z = add_rent_estimate(_zips())
    assert z.loc["A_census", "rent_est"] == 800 * 1.5
    assert z.loc["A_census", "rent_source"] == "census-scaled"


def test_small_metro_uses_the_national_ratio():
    assert 2 < MIN_ZIPS_FOR_METRO_RATIO     # metro B has too few ZIPs with both sources
    z = add_rent_estimate(_zips())
    national = 1.5   # median of the ratios: 5 x 1.5 and 1 x 1.2
    assert z.loc["B_census", "rent_est"] == 1000 * national


def test_no_data_falls_back_to_metro_median_and_never_overwrites():
    z = add_rent_estimate(_zips())
    assert z.loc["A_none", "rent_source"] == "metro-median"
    assert z.loc["A_none", "rent_est"] == z[z.cbsa_code == "A"]["zori_latest"].median()
    assert z["rent_est"].notna().all()


def test_tables_without_the_inputs_are_returned_unchanged():
    z = pd.DataFrame({"zcta": ["1"], "cbsa_code": ["A"]})
    assert "rent_est" not in add_rent_estimate(z)


def test_implausibly_low_census_rent_is_ignored():
    z = _zips()
    z.loc["A_census", "median_gross_rent"] = 99.0      # bottom-coded ACS value
    out = add_rent_estimate(z)
    assert out.loc["A_census", "rent_source"] == "metro-median"   # not a $148 "estimate"
