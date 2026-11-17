"""Pull ACS demographics for the area around an office."""
from .client import CensusClient
from .geocode import locate_address, locate_point

DATASET = "{year}/acs/acs5"

# label -> ACS variable
VARIABLES = {
    "population": "B01003_001E",
    "median_age": "B01002_001E",
    "median_household_income": "B19013_001E",
    "median_home_value": "B25077_001E",
    "median_gross_rent": "B25064_001E",
    "labor_force": "B23025_003E",
    "unemployed": "B23025_005E",
    "pop_25_plus": "B15003_001E",
    "bachelors": "B15003_022E",
    "masters": "B15003_023E",
    "professional": "B15003_024E",
    "doctorate": "B15003_025E",
}


def _num(v):
    # Census uses large negative sentinels (e.g. -666666666) for "not available"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n < -999999 else n


def _derive(d):
    d = dict(d)
    lf, un = d.pop("labor_force"), d.pop("unemployed")
    d["unemployment_rate_pct"] = round(100 * un / lf, 1) if lf and un is not None else None
    base = d.pop("pop_25_plus")
    degs = [d.pop(k) for k in ("bachelors", "masters", "professional", "doctorate")]
    d["bachelors_or_higher_pct"] = (
        round(100 * sum(degs) / base, 1) if base and all(x is not None for x in degs) else None
    )
    return d


# Five most recent ACS 5-Year vintages (2020-2024 = the 2020-2024 release, etc.)
DEFAULT_YEARS = (2020, 2021, 2022, 2023, 2024)


def office_profile(address=None, lat=None, lon=None, years=DEFAULT_YEARS, client=None):
    """Return {'location': {...}, 'years': {year: {'tract':..., 'county':..., 'state':...}}}.

    Provide either `address` or both `lat` and `lon`. The location is geocoded once;
    each year in `years` is one ACS 5-Year vintage. A year that fails (e.g. not yet
    published, or tract boundaries changed) is recorded as {'error': ...}.
    """
    if isinstance(years, int):
        years = (years,)
    if address:
        loc = locate_address(address)
    elif lat is not None and lon is not None:
        loc = locate_point(lat, lon)
    else:
        raise ValueError("Provide address= or lat= and lon=")

    c = client or CensusClient()
    out = {"location": loc, "years": {}}
    for year in years:
        try:
            out["years"][year] = _profile_for_year(c, loc, year)
        except Exception as e:  # keep the other years if one vintage fails
            out["years"][year] = {"error": f"{type(e).__name__}: {e}"}
    return out


def _profile_for_year(c, loc, year):
    ds = DATASET.format(year=year)
    names = list(VARIABLES)
    get = ["NAME"] + [VARIABLES[n] for n in names]
    st, co, tr = loc["state"], loc["county"], loc["tract"]
    levels = {
        "tract": {"for": f"tract:{tr}", "in": f"state:{st} county:{co}"},
        "county": {"for": f"county:{co}", "in": f"state:{st}"},
        "state": {"for": f"state:{st}"},
    }
    out = {"acs_year": year}
    for level, geo in levels.items():
        row = c.query(ds, get, geo)[0]
        vals = {n: _num(row[VARIABLES[n]]) for n in names}
        out[level] = {"name": row["NAME"], **_derive(vals)}
    return out
