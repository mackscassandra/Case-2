"""Minimal client for the Census Data API (https://api.census.gov/data.html)."""
import os
from pathlib import Path

import requests

BASE_URL = "https://api.census.gov/data"
MAX_VARIABLES = 50  # per the API user guide


def _load_dotenv(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


class CensusClient:
    def __init__(self, api_key=None):
        _load_dotenv()
        self.api_key = api_key or os.environ.get("CENSUS_API_KEY")
        if not self.api_key:
            raise ValueError("Set CENSUS_API_KEY in .env or pass api_key=")

    def query(self, dataset, get, geography, extra=None, group=None):
        """Run a query.

        dataset:   path after /data, e.g. "2022/acs/acs5"
        get:       list of variable names (max 50)
        geography: dict of predicates, e.g. {"for": "state:*"}
        extra:     other predicates, e.g. {"DATE_": "7"}
        group:     optional table group, fetches all variables via get=group(B01001)
        Returns a list of dicts (header row used as keys).
        """
        get = list(get or [])
        if len(get) > MAX_VARIABLES:
            raise ValueError(f"Max {MAX_VARIABLES} variables per query")
        if group:
            get.append(f"group({group})")
        params = {"get": ",".join(get), **geography, **(extra or {}), "key": self.api_key}
        r = requests.get(f"{BASE_URL}/{dataset}", params=params, timeout=30)
        r.raise_for_status()
        header, *rows = r.json()
        return [dict(zip(header, row)) for row in rows]
