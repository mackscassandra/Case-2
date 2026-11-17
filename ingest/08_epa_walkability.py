"""EPA National Walkability Index (block groups) -> population-weighted score per ZIP.

Free, no key. Scores run 1 (least walkable) to 20 (most). The file is a ~400 MB
geodatabase, so the first run takes a few minutes. Run 01_geography.py first.
"""
import geopandas as gpd
import pandas as pd
import pyogrio

from common import PROCESSED, RAW, download, save, unzip

URL = "https://edg.epa.gov/EPADataCommons/public/OA/WalkabilityIndex.zip"
WANT = ["GEOID10", "CBSA", "TotPop", "NatWalkInd", "D3B_Ranked", "D4A_Ranked"]


def main():
    print("EPA National Walkability Index")
    folder = unzip(download(URL, RAW / "epa" / "WalkabilityIndex.zip"))
    gdb = next(folder.rglob("*.gdb"))
    layer = pyogrio.list_layers(gdb)[0][0]
    cols = [c for c in WANT if c in pyogrio.read_info(gdb, layer=layer)["fields"]]
    bg = gpd.read_file(gdb, layer=layer, columns=cols)
    print(f"  {len(bg):,} block groups; columns used: {cols}")

    pts = bg.copy()
    pts["geometry"] = bg.representative_point()
    zcta = gpd.read_parquet(PROCESSED / "geo_zcta.parquet")[["zcta", "geometry"]].to_crs(bg.crs)
    j = gpd.sjoin(pts, zcta, how="inner", predicate="within")

    w = j["TotPop"].clip(lower=1)
    score_cols = [c for c in ["NatWalkInd", "D3B_Ranked", "D4A_Ranked"] if c in j]
    agg = (j[score_cols].mul(w, axis=0).groupby(j["zcta"]).sum()
           .div(w.groupby(j["zcta"]).sum(), axis=0)).reset_index()
    agg = agg.rename(columns={"NatWalkInd": "walk_index", "D3B_Ranked": "street_density_rank",
                              "D4A_Ranked": "transit_proximity_rank"})
    save(agg, "epa_walkability_zip")


if __name__ == "__main__":
    main()
