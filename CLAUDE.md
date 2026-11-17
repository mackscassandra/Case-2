# Project context for Claude Code

## Goal
Recommend a Big 4 firm × office × service line, a metro and a neighborhood (ZIP) to McCombs MPA graduates, based on their inputs, on a live US map. Class project; AI use is encouraged.

## Layout
- `ingest/` — one script per data source, numbered in run order; `common.py` has shared helpers (`download`, `get_json`, `save`, `api_key`).
- `ingest/build_tables.py` — joins everything into `zip_features` and `metro_features`.
- `data/raw/` — downloads (git-ignored). `data/processed/` — Parquet outputs (committed). `data/manual/` — hand-entered CSVs.
- `app/` — Streamlit app (to be built).

## Join keys (always strings, zero-padded)
- `zcta` — 5-digit ZIP Code Tabulation Area
- `county_fips` — 5 digits (state 2 + county 3)
- `cbsa_code` — 5-digit metro/micro area code (2023 delineation)
- `state_fips` — 2 digits; `state` — 2-letter postal code

## Rules
- Every new data source = a new numbered script in `ingest/` that writes one Parquet file through `save()`.
- Record the data year in a column (e.g. `acs_year`, `rpp_year`).
- Never call paid APIs at app runtime; precompute in `ingest/`.
- Census sentinel values (negative numbers like -666666666) become NaN.
- Political data is display-only; never include it in the recommendation score.
- After changing a script, run it and report row counts, null shares and 3 spot-checked cities (Austin 12420, New York 35620, Chicago 16980).
