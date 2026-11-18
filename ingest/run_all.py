"""Run every ingest step in order, keep going past failures, and print a summary.

  python ingest/run_all.py              # everything except the optional Google step
  python ingest/run_all.py --with-google
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
STEPS = [
    "01_geography.py", "01b_offices.py", "02_census_acs.py", "03_bea_rpp.py", "04_bls_oews.py",
    "05_zillow.py", "06_elections.py", "07_fema_nri.py", "08_epa_walkability.py",
    "09_osm_amenities.py", "10_google_places_cafes.py", "11_fbi_crime.py",
    "12_census_offices.py", "16_census_offices_county.py", "build_tables.py",
]


def main():
    results = {}
    for step in STEPS:
        if step.startswith("10_") and "--with-google" not in sys.argv:
            results[step] = "skipped (optional)"
            continue
        print(f"\n=== {step} ===")
        code = subprocess.call([sys.executable, step], cwd=HERE)
        results[step] = "ok" if code == 0 else f"FAILED (exit {code})"
    print("\nSummary")
    for step, status in results.items():
        print(f"  {step:32s} {status}")


if __name__ == "__main__":
    main()
