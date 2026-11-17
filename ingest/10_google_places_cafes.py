"""OPTIONAL: cafe ratings and open/closed status from Google Places API (New).

Adds quality to the OpenStreetMap cafe counts. One Nearby Search per ZIP in the
target metros, capped by MAX_CALLS so the team stays inside Google's free monthly
allowance. Requesting rating fields bills at a higher tier with a smaller free cap,
so check https://developers.google.com/maps/billing-and-pricing/pricing before raising
MAX_CALLS, and set a budget cap in Google Cloud. Needs GOOGLE_PLACES_API_KEY.
Run 01_geography.py and 09_osm_amenities.py first.
"""
import json
import os
import time

import pandas as pd
import requests

from common import PROCESSED, RAW, api_key, save

MAX_CALLS = int(os.getenv("PLACES_MAX_CALLS", "900"))
URL = "https://places.googleapis.com/v1/places:searchNearby"
FIELDS = ("places.id,places.displayName,places.location,places.rating,"
          "places.userRatingCount,places.businessStatus")


def main():
    key = api_key("GOOGLE_PLACES_API_KEY")
    zcta = pd.read_parquet(PROCESSED / "geo_zcta.parquet", columns=["zcta", "lat", "lon", "land_sqmi", "cbsa_code"])
    metros = pd.read_parquet(PROCESSED / "osm_points.parquet", columns=["cbsa_code"])["cbsa_code"].unique()
    targets = zcta[zcta["cbsa_code"].isin(metros)].sort_values("cbsa_code")
    cache = RAW / "google_places"
    cache.mkdir(parents=True, exist_ok=True)

    calls, rows = 0, []
    for z in targets.itertuples():
        f = cache / f"{z.zcta}.json"
        if not f.exists():
            if calls >= MAX_CALLS:
                print(f"  reached MAX_CALLS={MAX_CALLS}; rerun next month to continue")
                break
            radius = min(5000, max(800, (z.land_sqmi ** 0.5) * 1609 / 2))
            body = {"includedTypes": ["cafe", "coffee_shop"], "maxResultCount": 20,
                    "locationRestriction": {"circle": {"center": {"latitude": z.lat, "longitude": z.lon},
                                                       "radius": radius}}}
            r = requests.post(URL, json=body, timeout=30,
                              headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS})
            r.raise_for_status()
            f.write_text(r.text)
            calls += 1
            time.sleep(0.1)
        for p in json.loads(f.read_text()).get("places", []):
            rows.append({"zcta": z.zcta, "place_id": p["id"],
                         "name": p.get("displayName", {}).get("text"),
                         "rating": p.get("rating"), "n_ratings": p.get("userRatingCount"),
                         "status": p.get("businessStatus")})
    print(f"  API calls this run: {calls}")
    df = pd.DataFrame(rows).drop_duplicates("place_id")
    df = df[df["status"].fillna("OPERATIONAL") == "OPERATIONAL"]
    agg = df.groupby("zcta").agg(gp_cafes=("place_id", "count"), gp_cafe_rating=("rating", "mean"),
                                 gp_cafes_4plus=("rating", lambda s: (s >= 4.3).sum())).reset_index()
    save(agg, "google_cafes_zip")


if __name__ == "__main__":
    main()
