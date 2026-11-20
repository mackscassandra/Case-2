"""SYNTHETIC demo tables, used only when data/processed/ has not been built yet.

The numbers are made up so the app can be tried before the pipeline has run. The app
shows a warning banner whenever it is using them.
"""
from __future__ import annotations

import pandas as pd


def demo_tables() -> dict[str, pd.DataFrame]:
    metro = pd.DataFrame({
        "cbsa_code": ["12420", "35620", "16980", "42660", "19740", "33100"],
        "cbsa_name": ["Austin-Round Rock-San Marcos, TX", "New York-Newark-Jersey City, NY-NJ",
                      "Chicago-Naperville-Elgin, IL-IN", "Seattle-Tacoma-Bellevue, WA",
                      "Denver-Aurora-Centennial, CO", "Miami-Fort Lauderdale-West Palm Beach, FL"],
        "rpp_all": [101, 125, 106, 115, 108, 111],
        "rpp_housing": [105, 160, 115, 140, 125, 135],
        "wage_multiplier": [1.00, 1.30, 1.10, 1.15, 1.05, 1.00],
        "violent_per_100k": [400, 350, 550, 450, 500, 420],
        "property_per_100k": [2500, 1500, 2200, 3500, 3000, 2600],
        "pct_age_22_34": [0.24, 0.20, 0.19, 0.22, 0.21, 0.17],
    })
    offices = pd.DataFrame({
        "firm": ["Deloitte", "PwC", "EY", "KPMG", "Deloitte", "EY", "KPMG"],
        "office_name": ["Austin", "New York", "Chicago", "Seattle", "Denver", "Miami", "Austin"],
        "cbsa_code": ["12420", "35620", "16980", "42660", "19740", "33100", "12420"],
        "city": ["Austin", "New York", "Chicago", "Seattle", "Denver", "Miami", "Austin"],
        "state": ["TX", "NY", "IL", "WA", "CO", "FL", "TX"],
        "lat": [30.27, 40.75, 41.88, 47.61, 39.74, 25.77, 30.26],
        "lon": [-97.74, -73.98, -87.63, -122.33, -104.99, -80.19, -97.75],
        "audit": ["Y", "Y", "Y", "Y", "Y", "Y", "N"],
        "tax": ["Y", "", "Y", "Y", "Y", "Y", "Y"],
        "advisory": ["Y"] * 7,
    })
    state_taxes = pd.DataFrame({
        "state": ["TX", "NY", "IL", "WA", "CO", "FL"],
        "has_wage_income_tax": ["N", "Y", "Y", "N", "Y", "N"],
        "income_tax_rate_at_75k": ["0", "5", "4.95", "0", "4.4", "0"],
    })
    local_taxes = pd.DataFrame({"city": ["New York"], "state": ["NY"], "cbsa_code": [None],
                                "resident_rate": ["3"], "nonresident_rate": ["0"]})
    rows = []
    for f, lo, hi in [("Deloitte", 70000, 80000), ("PwC", 72000, 82000),
                      ("EY", 70000, 80000), ("KPMG", 71000, 79000)]:
        for line in ("Audit", "Tax", "Advisory"):
            rows.append({"firm": f, "service_line": line, "salary_low": lo, "salary_high": hi})
    zips = pd.DataFrame({
        "zcta": ["78701", "78704", "78745", "78613", "98101", "98103"],
        "cbsa_code": ["12420"] * 4 + ["42660"] * 2,
        "lat": [30.27, 30.24, 30.21, 30.50, 47.61, 47.67],
        "lon": [-97.74, -97.77, -97.80, -97.82, -122.33, -122.34],
        "zori_latest": [2400, 2000, 1500, 1600, 2600, 2200],
        "rent_est": [2400, 2000, 1500, 1600, 2600, 2200],
        "rent_source": ["zillow"] * 6,
        "walk_index": [18, 15, 10, 6, 19, 16],
        "pct_transit": [0.06, 0.04, 0.02, 0.01, 0.20, 0.15],
        "per_sqmi_gym": [10, 6, 2, 1, 12, 7], "per_sqmi_park": [3, 4, 2, 1, 3, 5],
        "n_trail": [1, 3, 2, 0, 1, 2],
        "per_sqmi_cafe": [20, 12, 3, 1, 25, 15], "per_sqmi_restaurant": [60, 30, 10, 4, 70, 40],
        "per_sqmi_bar": [30, 12, 2, 1, 25, 10],
        "pct_age_22_34": [0.45, 0.35, 0.22, 0.15, 0.40, 0.38],
        "per_sqmi_childcare": [0.5, 1.5, 2.5, 3.0, 0.4, 1.0],
        "pct_hh_with_kids": [0.08, 0.18, 0.35, 0.42, 0.05, 0.15],
    })
    return {"metro": metro, "offices": offices, "state_taxes": state_taxes,
            "local_taxes": local_taxes, "salary_base": pd.DataFrame(rows), "zip": zips}
