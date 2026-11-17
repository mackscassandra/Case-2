"""Zillow Research rent (ZORI) and home value (ZHVI) indexes by ZIP. No key needed.

Zillow's public CSVs are free to use with attribution: "Data from Zillow Research".
"""
import pandas as pd

from common import RAW, download, save

BASE = "https://files.zillowstatic.com/research/public_csvs"
FILES = {
    "zori": f"{BASE}/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv",
    "zhvi": f"{BASE}/zhvi/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
}


def latest(name: str) -> pd.DataFrame:
    path = download(FILES[name], RAW / "zillow" / f"{name}.csv", force=True)
    df = pd.read_csv(path, dtype={"RegionName": str})
    dates = sorted(c for c in df.columns if c[:2] in ("19", "20"))
    vals = df[dates]
    last = vals.ffill(axis=1).iloc[:, -1]
    year_ago = vals.ffill(axis=1).iloc[:, -13] if len(dates) > 12 else pd.NA
    return pd.DataFrame({
        "zcta": df["RegionName"].str.zfill(5),
        f"{name}_latest": last,
        f"{name}_yoy": last / year_ago - 1,
        f"{name}_month": dates[-1],
    })


def main():
    print("Zillow ZORI + ZHVI")
    out = latest("zori").merge(latest("zhvi"), on="zcta", how="outer")
    save(out, "zillow_zip")


if __name__ == "__main__":
    main()
