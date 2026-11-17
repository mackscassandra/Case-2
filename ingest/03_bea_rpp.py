"""BEA Regional Price Parities (cost of living index, US = 100) by metro and state.

Needs BEA_API_KEY (free: https://apps.bea.gov/api/signup/).
Line 1 = all items; line 3 = housing (rents).
"""
import pandas as pd

from common import api_key, get_json, save

URL = "https://apps.bea.gov/api/data"
LINES = {1: "rpp_all", 3: "rpp_housing"}


def fetch(table: str, geofips: str) -> pd.DataFrame:
    frames = []
    for line, col in LINES.items():
        js = get_json(URL, {"UserID": api_key("BEA_API_KEY"), "method": "GetData",
                            "datasetname": "Regional", "TableName": table, "LineCode": line,
                            "GeoFips": geofips, "Year": "LAST5", "ResultFormat": "json"})
        res = js["BEAAPI"]["Results"]
        if "Error" in res or "Data" not in res:
            raise SystemExit(f"BEA error for {table} line {line}: {res.get('Error', res)}")
        d = pd.DataFrame(res["Data"])
        d["DataValue"] = pd.to_numeric(d["DataValue"].str.replace(",", ""), errors="coerce")
        latest = d["TimePeriod"].max()
        d = d[d["TimePeriod"] == latest][["GeoFips", "GeoName", "DataValue"]]
        frames.append(d.rename(columns={"DataValue": col}).assign(rpp_year=int(latest)))
    out = frames[0].merge(frames[1][["GeoFips", "rpp_housing"]], on="GeoFips", how="left")
    return out


def main():
    print("BEA RPP by metro")
    msa = fetch("MARPP", "MSA").rename(columns={"GeoFips": "cbsa_code", "GeoName": "bea_name"})
    save(msa, "bea_rpp_cbsa")
    print("BEA RPP by state")
    st = fetch("SARPP", "STATE").rename(columns={"GeoFips": "state_fips", "GeoName": "state_name"})
    st["state_fips"] = st["state_fips"].str[:2]
    save(st, "bea_rpp_state")


if __name__ == "__main__":
    main()
