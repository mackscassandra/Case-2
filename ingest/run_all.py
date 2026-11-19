"""Run every ingest step in order, keep going past failures, and print a summary.

  python ingest/run_all.py              # everything except the optional Google step
  python ingest/run_all.py --with-google
  python ingest/run_all.py --skip 09_osm_amenities.py   # leave a step to another workflow
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
STEPS = [
    "01_geography.py", "01b_offices.py", "02_census_acs.py", "03_bea_rpp.py", "04_bls_oews.py",
    "05_zillow.py", "06_elections.py", "08_epa_walkability.py",
    "09_osm_amenities.py", "10_google_places_cafes.py", "11_fbi_crime.py",
    "12_census_offices.py", "16_noaa_climate.py", "17_census_offices_county.py", "build_tables.py",
]


def main():
    skip = {sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--skip"}
    results = {}
    for step in STEPS:
        if step.startswith("10_") and "--with-google" not in sys.argv:
            results[step] = "skipped (optional)"
            continue
        if step in skip:
            results[step] = "skipped (--skip)"
            continue
        print(f"\n=== {step} ===")
        code = subprocess.call([sys.executable, step], cwd=HERE)
        results[step] = "ok" if code == 0 else f"FAILED (exit {code})"
    print("\nSummary")
    for step, status in results.items():
        print(f"  {step:32s} {status}")


if __name__ == "__main__":
    main()
