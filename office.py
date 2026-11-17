"""CLI: python office.py "1600 Pennsylvania Ave NW, Washington, DC"  [--years 2020 2021 2022 2023 2024]
       python office.py --lat 30.2849 --lon -97.7341
"""
import argparse
import json

from census.office import DEFAULT_YEARS, office_profile

p = argparse.ArgumentParser()
p.add_argument("address", nargs="?")
p.add_argument("--lat", type=float)
p.add_argument("--lon", type=float)
p.add_argument("--years", type=int, nargs="+", default=list(DEFAULT_YEARS), help="ACS 5-year vintages")
a = p.parse_args()
print(json.dumps(office_profile(a.address, a.lat, a.lon, a.years), indent=2))
