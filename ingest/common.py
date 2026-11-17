"""Shared helpers for every ingest script: paths, API keys, downloads, saving."""
from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MANUAL = ROOT / "data" / "manual"
for _p in (RAW, PROCESSED, MANUAL):
    _p.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")

# Several government sites (BLS especially) reject requests without a browser-like
# User-Agent. Put a real contact email in .env as CONTACT_EMAIL.
HEADERS = {
    "User-Agent": f"Mozilla/5.0 (McCombs MPA student project; {os.getenv('CONTACT_EMAIL', 'student@utexas.edu')})"
}


def api_key(name: str, required: bool = True) -> str | None:
    """Read an API key from .env. Fail with a clear message if it's missing."""
    val = os.getenv(name)
    if required and not val:
        raise SystemExit(f"Missing {name}. Copy .env.example to .env and fill it in.")
    return val


def download(url: str, dest: Path, force: bool = False, retries: int = 3) -> Path:
    """Stream a file to disk. Skips the download if the file already exists."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        print(f"  exists, skipping: {dest.relative_to(ROOT)}")
        return dest
    for attempt in range(1, retries + 1):
        try:
            print(f"  downloading {url}")
            with requests.get(url, headers=HEADERS, stream=True, timeout=120) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.rename(dest)
            return dest
        except requests.RequestException as e:
            print(f"  attempt {attempt} failed: {e}")
            time.sleep(3 * attempt)
    raise SystemExit(f"Could not download {url}")


def get_json(url: str, params: dict | None = None, retries: int = 3):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=120)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"  attempt {attempt} failed: {e}")
            time.sleep(3 * attempt)
    raise SystemExit(f"Request failed: {url}")


def unzip(path: Path, dest: Path | None = None) -> Path:
    dest = dest or path.with_suffix("")
    if not dest.exists():
        with zipfile.ZipFile(path) as z:
            z.extractall(dest)
    return dest


def save(df: pd.DataFrame, name: str) -> Path:
    """Save a processed table as Parquet and print a quick data-quality summary."""
    out = PROCESSED / f"{name}.parquet"
    df.to_parquet(out, index=False)
    nulls = df.isna().mean().sort_values(ascending=False).head(5)
    print(f"  saved {out.relative_to(ROOT)}: {len(df):,} rows x {df.shape[1]} cols")
    print("  highest null shares:", ", ".join(f"{c}={v:.0%}" for c, v in nulls.items()))
    return out


def zfill_fips(s: pd.Series, width: int) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(width)
