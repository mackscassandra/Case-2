"""NOAA 1991-2020 Climate Normals for every city with a Big 4 office.

Each office city is matched to the nearest NOAA first-order weather station
(USW... IDs, mostly airports; RQW... in Puerto Rico) with complete 30-year
temperature and precipitation normals; if the nearest lacks a value, the next
nearest is tried (up to 6). Many airports don't record snowfall or rainy days, so
those two gaps are filled from the nearest station of any network within 30 miles
that does, and every fill is logged in `fill_notes`. No key needed.

Outputs:
  climate_city.parquet / .csv   one row per office city (city, state, cbsa_code)
  climate_metro.parquet         one row per metro (median of its office cities)
Source: https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals
"""
import io
import math

import pandas as pd
import requests

from common import HEADERS, MANUAL, PROCESSED, RAW, download, save

BASE = "https://www.ncei.noaa.gov/data/normals-annualseasonal/1991-2020"
VARS = {
    "ANN-TAVG-NORMAL": "temp_avg_f",              # annual mean temperature
    "JJA-TMAX-NORMAL": "summer_high_f",           # Jun-Aug average daily high
    "DJF-TMIN-NORMAL": "winter_low_f",            # Dec-Feb average daily low
    "ANN-TMAX-AVGNDS-GRTH090": "days_90f_plus",   # days with high >= 90F
    "ANN-TMIN-AVGNDS-LSTH032": "days_below_32f",  # days with low <= 32F
    "ANN-PRCP-NORMAL": "precip_in",               # annual precipitation, inches
    "ANN-PRCP-AVGNDS-GE001HI": "rainy_days",      # days with >= 0.01 in precipitation
    "ANN-SNOW-NORMAL": "snow_in",                 # annual snowfall, inches
}
REQUIRED = ["ANN-TAVG-NORMAL", "JJA-TMAX-NORMAL", "DJF-TMIN-NORMAL", "ANN-PRCP-NORMAL"]
FILL = ["ANN-PRCP-AVGNDS-GE001HI", "ANN-SNOW-NORMAL"]
FILL_MILES = 30


def miles(lat1, lon1, lat2, lon2):
    r = math.pi / 180
    a = (math.sin((lat2 - lat1) * r / 2) ** 2
         + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2)
    return 2 * 3958.8 * math.asin(math.sqrt(a))


def inventory() -> pd.DataFrame:
    inv = download(f"{BASE}/doc/inventory_30yr.txt", RAW / "noaa" / "inventory_30yr.txt")
    rows = [(l[:11], float(l[12:20]), float(l[21:30]), l[41:71].strip())
            for l in inv.read_text().splitlines() if len(l) > 40]
    return pd.DataFrame(rows, columns=["station_id", "lat", "lon", "station_name"])


_cache: dict = {}


def normals(sid: str) -> dict | None:
    if sid not in _cache:
        r = requests.get(f"{BASE}/access/{sid}.csv", headers=HEADERS, timeout=60)
        _cache[sid] = pd.read_csv(io.StringIO(r.text)).iloc[0].to_dict() if r.ok else None
    return _cache[sid]


def num(rec, var):
    return pd.to_numeric(rec.get(var), errors="coerce") if rec else float("nan")


def main():
    print("NOAA climate normals for Big 4 office cities")
    off = pd.read_csv(MANUAL / "big4_offices.csv", dtype=str, keep_default_na=False)
    off["lat"], off["lon"] = off["lat"].astype(float), off["lon"].astype(float)
    cities = off.groupby(["city", "state", "cbsa_code"], as_index=False)[["lat", "lon"]].mean()
    inv = inventory()
    first_order = inv[inv["station_id"].str[:3].isin(["USW", "RQW"])].copy()

    rows = []
    for c in cities.itertuples():
        first_order["miles"] = [miles(c.lat, c.lon, a, b) for a, b in zip(first_order["lat"], first_order["lon"])]
        for s in first_order.nsmallest(6, "miles").itertuples():
            rec = normals(s.station_id)
            if rec and all(pd.notna(num(rec, v)) for v in REQUIRED):
                break
        else:
            print(f"  no complete station near {c.city}, {c.state}")
            continue
        row = {"city": c.city, "state": c.state, "cbsa_code": c.cbsa_code, "station_id": s.station_id,
               "station_name": s.station_name, "station_miles": round(s.miles, 1),
               **{new: num(rec, old) for old, new in VARS.items()}}
        notes = []
        for var in FILL:
            if pd.isna(row[VARS[var]]):
                inv["miles"] = [miles(s.lat, s.lon, a, b) for a, b in zip(inv["lat"], inv["lon"])]
                for n in inv[inv["miles"] <= FILL_MILES].nsmallest(15, "miles").itertuples():
                    val = num(normals(n.station_id), var)
                    if pd.notna(val):
                        row[VARS[var]] = val
                        notes.append(f"{VARS[var]} from {n.station_name} ({n.station_id}, {n.miles:.1f} mi)")
                        break
        row["fill_notes"] = "; ".join(notes)
        rows.append(row)

    city = pd.DataFrame(rows)
    city["normals_period"] = "1991-2020"
    save(city, "climate_city")
    city.to_csv(PROCESSED / "climate_city.csv", index=False)
    metro = city.groupby("cbsa_code", as_index=False)[list(VARS.values())].median()
    metro["normals_period"] = "1991-2020"
    save(metro, "climate_metro")


if __name__ == "__main__":
    main()
