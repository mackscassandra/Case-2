"""FEMA National Risk Index by county (natural hazard risk). No key needed."""
import pandas as pd

from common import RAW, download, save, unzip, zfill_fips

URL = ("https://hazards.fema.gov/nri/Content/StaticDocuments/DataDownload/"
       "NRI_Table_Counties/NRI_Table_Counties.zip")
KEEP = {"STCOFIPS": "county_fips", "RISK_SCORE": "nri_risk_score", "RISK_RATNG": "nri_risk_rating",
        "EAL_SCORE": "nri_expected_loss_score", "RESL_SCORE": "nri_resilience_score"}


def main():
    print("FEMA National Risk Index (counties)")
    folder = unzip(download(URL, RAW / "fema" / "NRI_Table_Counties.zip"))
    csv = next(folder.rglob("NRI_Table_Counties.csv"))
    df = pd.read_csv(csv, usecols=list(KEEP), dtype={"STCOFIPS": str}).rename(columns=KEEP)
    df["county_fips"] = zfill_fips(df["county_fips"], 5)
    save(df, "fema_nri_county")


if __name__ == "__main__":
    main()
