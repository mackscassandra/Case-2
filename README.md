# Big 4 Firm & City Recommender

A web app that recommends a Big 4 firm, office, metro and neighborhood to soon-to-be McCombs MPA graduates, shown on a live US map. This repo holds the data pipeline; the Streamlit app comes next.

## Quick start

```bash
git clone <this repo> && cd big4-recommender
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then paste in your free API keys
python ingest/run_all.py    # downloads, cleans and builds everything (~20-40 min first run)
```

Re-running is cheap: downloaded files are cached in `data/raw/` and skipped.

## Free API keys you need

| Key | Used by | Sign up |
| --- | --- | --- |
| `CENSUS_API_KEY` | 02_census_acs | https://api.census.gov/data/key_signup.html |
| `BEA_API_KEY` | 03_bea_rpp | https://apps.bea.gov/api/signup/ |
| `FBI_API_KEY` | 11_fbi_crime | https://api.data.gov/signup/ |
| `GOOGLE_PLACES_API_KEY` | 10_google_places_cafes (optional) | Google Cloud console; set a budget cap first |

## Datasets

| Step | Dataset | Level | Output (`data/processed/`) |
| --- | --- | --- | --- |
| 01b | Big 4 offices placed in metros and counties | office | `offices` |
| 01 | Census cartographic boundaries (CBSA 2023, county 2023, ZCTA 2020) | metro / county / ZIP | `geo_cbsa`, `geo_county`, `geo_zcta` |
| 02 | Census ACS 5-year: age, education, income, rent, home value, property tax, kids, commuting | ZIP + metro | `acs_zcta`, `acs_cbsa` |
| 03 | BEA Regional Price Parities (cost of living, US = 100) | metro + state | `bea_rpp_cbsa`, `bea_rpp_state` |
| 04 | BLS OEWS wages, Accountants & Auditors (13-2011) | metro | `bls_accountant_wages_cbsa` |
| 05 | Zillow ZORI rent + ZHVI home values | ZIP | `zillow_zip` |
| 06 | 2024 presidential results (display only) | county | `elections_county` |
| 07 | FEMA National Risk Index | county | `fema_nri_county` |
| 08 | EPA National Walkability Index | block group → ZIP | `epa_walkability_zip` |
| 09 | OpenStreetMap: cafes, restaurants, bars, gyms, parks, childcare, hiking trails | ZIP | `osm_points`, `osm_amenities_zip` |
| 10 | Google Places cafe ratings (optional) | ZIP | `google_cafes_zip` |
| 11 | FBI Crime Data Explorer (violent + property) | police agency → metro | `fbi_crime_agency` |
| build | Everything joined | ZIP + metro | `zip_features`, `metro_features` |

### Entered by hand (`data/manual/`)

- `big4_offices.csv` — 318 US offices for Deloitte (91), EY (82), KPMG (75) and PwC (70), from each firm's official office locator (Nov 18, 2026). `office_type` marks specialty sites (Deloitte Digital, EY wavespace, Deloitte University, etc.); `notes` flags entries that needed a fix. Service-line columns are blank: the firms don't publish them per office. `01b_offices.py` adds metro and county codes automatically.
- `salary_base.csv` — posted pay ranges from Big 4 job postings in pay-transparency states + the MPA employment report.
- `state_taxes.csv` — the no-wage-tax flag is filled; add rates from the Tax Foundation.
- `local_income_taxes.csv` — cities with local income tax (NYC, Philadelphia, etc.).

### Not yet built (stretch)

School quality (NCES + Stanford SEDA), NOAA climate normals, air quality, CPA licensure rules.

## What goes in GitHub

`data/processed/` and `data/manual/` are committed so teammates can run the app without re-downloading. `data/raw/` and `.env` are git-ignored. GitHub rejects files over 100 MB: if a processed file gets that big, use Git LFS or drop the geometry column.

## Data attribution

Census Bureau, BEA, BLS, FBI, FEMA, EPA (public domain); Zillow Research; © OpenStreetMap contributors (ODbL); Google Places (display terms apply).

## Census API helper

`census/client.py` (with `example.py`) is a small general-purpose client for ad-hoc Census Data API queries. The pipeline's `ingest/02_census_acs.py` pulls the ACS tables the app needs; use the client for quick exploration.

## Notes (from the API User Guide)
- Max 50 variables per query; a key is required on every request (`&key=...`).
- Use `group(TABLE)` to get all variables in a table.

## Office-location lookup
Give an office address (or lat/lon) and get ACS 5-Year demographics for its census **tract**, **county** and **state**, for each of the five most recent vintages (2020-2024 by default; change with `--years`):

```bash
python office.py "110 Inner Campus Dr, Austin, TX 78712"
python office.py --lat 30.2849 --lon -97.7341 --years 2020 2021 2022 2023 2024
```

Or from Python: `from census import office_profile; office_profile(address="...")`.

Steps: the free [Census Geocoder](https://geocoding.geo.census.gov/) turns the location into state/county/tract FIPS codes, then the Census Data API returns population, median age, household income, home value, rent, unemployment rate and bachelor's-or-higher share. Edit `VARIABLES` in `census/office.py` to pull other variables.

## Job-listing data (WageScape via Dewey)

`ingest/14_wagescape_jobs.py` pulls Big 4 job postings from Dewey (2022 onward) and writes `data/processed/wagescape/`. It runs on GitHub, not in `run_all.py`, because it needs Python 3.12+ and a large download:

1. Add the Dewey key as a repository secret named `DEWEY_API_KEY` (Settings → Secrets and variables → Actions).
2. Go to the **Actions** tab → **Pull and clean Dewey data** → **Run workflow**.
3. Results are committed to `data/processed/wagescape/` (files under ~95 MB) and also attached to the run as a downloadable artifact.

Its packages are in `requirements-wagescape.txt`, kept separate so the main install still works on older Python versions.

### Coding audit / tax / advisory per office

Once the WageScape run has committed `data/processed/wagescape/`, run:

```bash
git pull
python ingest/15_office_service_lines.py --inspect   # check the columns it detected
python ingest/15_office_service_lines.py             # writes 1/0 into big4_offices.csv
```

An office gets **1** for a service line when its firm posted at least 3 jobs in that line in the office's metro since 2022 (change with `SERVICE_MIN_POSTINGS` in `.env`), otherwise **0**. Postings name a city, not a building, so a firm's offices in one metro share codes. Specialty sites (`office_type = specialty`) are left blank to code by hand. The counts behind every code are saved to `data/processed/office_service_postings.csv`.
