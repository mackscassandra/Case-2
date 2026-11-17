# Case 2 – Census Data API

Small Python client for the [Census Data API](https://api.census.gov/data.html).

## Setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and set `CENSUS_API_KEY` (free key: https://www.census.gov/data/developers.html). `.env` is gitignored.
3. `python example.py`

## Notes (from the API User Guide)
- Max 50 variables per query; a key is required on every request (`&key=...`).
- Use `group(TABLE)` to get all variables in a table.
