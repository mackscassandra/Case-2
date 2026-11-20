# Why ZIP rent is estimated (`rent_est`)

**Decision (2026-11-20):** `zip_features` has a `rent_est` column (and `rent_source`) that fills in
rent for ZIPs where Zillow has none. The app scores and filters on `rent_est`, not on raw Zillow rent.

## The problem
Zillow's public ZORI file (`ingest/05_zillow.py`) covers only **8,355 of ~33,800 ZIPs (~25%)**.
In the 89 metros with a Big 4 office, **52%** of ZIPs have Zillow rent (5,666 of 10,959); Zillow
publishes more for urban ZIPs. This is a limit of Zillow's data, not a bug: the script already takes
each ZIP's last non-empty month, and the raw file has no more rows to read.

## Options considered
| Option | Why not / why |
| --- | --- |
| Leave rent blank; the app fills the median and flags low confidence | Half the neighborhoods in each metro would look average on rent, whatever they really cost |
| Drop rent as a criterion and use home value instead | Throws away good data where Zillow has it; home value is a poor proxy for what a graduate pays in rent |
| Use raw Census median gross rent | Covers 86% of those ZIPs, but runs low next to market rent (median Zillow/Census ratio 1.22) and is a 5-year average |
| **Census rent scaled to Zillow's level (chosen)** | Covers 86%, and was the most accurate fallback in testing |

## The test
On the 5,660 ZIPs in office metros that have both Zillow and Census rent (metros with at least 5
such ZIPs), predicting Zillow rent from Census rent:

| Method | Median absolute % error |
| --- | --- |
| Census rent x the metro's own Zillow/Census ratio | **11.2%** |
| Census rent x the national ratio | 12.7% |
| Census rent, unscaled | 18.3% |

The correlation between the two sources is only 0.46, so individual ZIPs can be off by much more
than 11%. The estimate is good enough to rank neighborhoods, not to quote a rent.

## How `rent_est` is built (`add_rent_estimate` in `ingest/build_tables.py`)
1. `zillow`: the ZIP's Zillow rent, if it has one.
2. `census-scaled`: else Census median gross rent x the metro's median Zillow/Census ratio
   (national median if the metro has fewer than 5 ZIPs with both).
3. `metro-median`: else the metro's median Zillow rent.
4. Blank if none of these exist; the scorer then fills the median and flags low confidence.

## Coverage in Big 4 metros (before this change: 52% from Zillow alone)
Share of the 10,959 ZIPs in the 89 Big 4 metros, by `rent_source`:

| Source | Share |
| --- | --- |
| zillow | 51.7% |
| census-scaled | 34.0% |
| metro-median | 14.2% |
| none | 0.1% |

Austin, New York and Chicago have a rent for every ZIP; their median `rent_est` is $1,652, $2,900
and $1,933. The 14% on `metro-median` are the weakest: they all get the same rent as every other ZIP
in their metro, so treat the neighborhood ranking on rent as least informative there.

## Caveats
- Census rents under $300 (bottom-coded values for a few tiny rural ZIPs, e.g. $99) are ignored, and
  top-coded values ($3,501) understate rent in the most expensive ZIPs.
- Zillow itself reports $40,000-$112,000 for 8 Hamptons ZIPs (11930-11976), which look like seasonal
  rentals. We keep Zillow's values as published; scoring is rank-based so they do not skew rankings,
  but they look odd on screen.
- Estimated rents are not real listings; the app shows `rent_source` so they can be told apart.
- ACS rent is a 5-year average and lags the market. Re-check the 1.22 ratio and the error figures
  when the ACS year or the Zillow file changes.
- The "max monthly rent" filter applies to `rent_est`, so it can include or exclude a ZIP on an
  estimate.
