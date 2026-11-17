"""Resolve an office location to Census geographies via the free Census Geocoder."""
import requests

GEOCODER = "https://geocoding.geo.census.gov/geocoder/geographies"
_COMMON = {"benchmark": "Public_AR_Current", "vintage": "Current_Current", "format": "json"}


def _pick(geos):
    tract = geos["Census Tracts"][0]
    return {
        "state": tract["STATE"],
        "county": tract["COUNTY"],
        "tract": tract["TRACT"],
        "county_name": (geos.get("Counties") or [{}])[0].get("NAME"),
        "state_name": (geos.get("States") or [{}])[0].get("NAME"),
    }


def locate_address(address):
    r = requests.get(f"{GEOCODER}/onelineaddress", params={"address": address, **_COMMON}, timeout=30)
    r.raise_for_status()
    matches = r.json()["result"]["addressMatches"]
    if not matches:
        raise LookupError(f"No geocoder match for address: {address!r}")
    m = matches[0]
    out = _pick(m["geographies"])
    out.update(matched_address=m["matchedAddress"], lon=m["coordinates"]["x"], lat=m["coordinates"]["y"])
    return out


def locate_point(lat, lon):
    r = requests.get(f"{GEOCODER}/coordinates", params={"x": lon, "y": lat, **_COMMON}, timeout=30)
    r.raise_for_status()
    geos = r.json()["result"]["geographies"]
    if not geos.get("Census Tracts"):
        raise LookupError(f"No census tract found at ({lat}, {lon}); is it inside the US?")
    out = _pick(geos)
    out.update(matched_address=None, lat=lat, lon=lon)
    return out
