"""BLS OEWS wages for Accountants and Auditors (SOC 13-2011) by metro.

Produces a salary multiplier per metro (metro median / national median) that scales
the base Big 4 salary to every city. No API key; BLS needs the User-Agent in common.py.
"""
import pandas as pd

from common import RAW, download, save, unzip

SOC = "13-2011"
YEARS = ["25", "24", "23"]  # newest first; the script uses the first that downloads
BASE = "https://www.bls.gov/oes/special-requests"
WAGE_COLS = ["TOT_EMP", "A_MEAN", "A_PCT10", "A_PCT25", "A_MEDIAN", "A_PCT75", "A_PCT90"]


def load(kind: str, yy: str) -> pd.DataFrame:
    z = download(f"{BASE}/oesm{yy}{kind}.zip", RAW / "bls" / f"oesm{yy}{kind}.zip")
    folder = unzip(z)
    prefix = "msa" if kind == "ma" else "national"  # the ma zip also holds a nonmetro (BOS) file
    xlsx = next(p for p in folder.rglob("*.xlsx") if p.name.lower().startswith(prefix))
    df = pd.read_excel(xlsx, dtype=str)
    df.columns = df.columns.str.upper()
    df = df[df["OCC_CODE"] == SOC].copy()
    df[WAGE_COLS] = df[WAGE_COLS].apply(pd.to_numeric, errors="coerce")  # '*' and '#' -> NaN
    return df


def main():
    for yy in YEARS:
        try:
            metro, nat = load("ma", yy), load("nat", yy)
            break
        except SystemExit as e:
            print(f"  20{yy} not available ({e}); trying an older year")
    else:
        raise SystemExit("No OEWS year could be downloaded")

    nat_median = nat["A_MEDIAN"].iloc[0]
    out = metro.rename(columns={"AREA": "cbsa_code", "AREA_TITLE": "bls_area"})
    out = out[["cbsa_code", "bls_area"] + WAGE_COLS]
    out.columns = [c.lower() for c in out.columns]
    out["wage_multiplier"] = out["a_median"] / nat_median
    out["oews_year"] = 2000 + int(yy)
    print(f"  national median accountant wage 20{yy}: ${nat_median:,.0f}")
    save(out, "bls_accountant_wages_cbsa")


if __name__ == "__main__":
    main()
