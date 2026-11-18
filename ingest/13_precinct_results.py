"""2024 presidential results by precinct (New York Times), rolled up to ZIP (ZCTA).

Display-only political layer; never used in the recommendation score.

Source: https://github.com/nytimes/presidential-precinct-map-2024
License: NYT Computational Use of Data Agreement (non-commercial). Any public display
must credit The New York Times and link to
https://www.nytimes.com/interactive/2025/us/elections/2024-election-map-precinct-results.html

Coverage gaps (per NYT): some counties/states have no usable precinct data; most of
New England is town-level; some boundaries are estimated (official_boundary=False).
Use county results (06_elections.py) wherever a ZIP has no precinct coverage.

Outputs (no geometry, small enough for GitHub):
  elections_precinct.parquet  one row per precinct
  elections_zip.parquet       votes summed to ZIP by each precinct's interior point
Run 01_geography.py first. No key needed.
"""
import geopandas as gpd
import pandas as pd

from common import PROCESSED, RAW, download, save

BASE = "https://int.nyt.com/newsgraphics/elections/map-data/2024/national"
NATIONAL = f"{BASE}/precincts-with-results.topojson.gz"
STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
          "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
COLS = ["state", "GEOID", "votes_dem", "votes_rep", "votes_total", "official_boundary"]


def load_precincts() -> gpd.GeoDataFrame:
    """National TopoJSON first; per-state GeoJSON if GDAL can't read the national file."""
    try:
        path = download(NATIONAL, RAW / "elections" / "precincts_2024.topojson.gz")
        gdf = gpd.read_file(f"/vsigzip/{path}")
        print(f"  read national file: {len(gdf):,} precincts")
        return gdf
    except (Exception, SystemExit) as e:  # download() raises SystemExit on failure
        print(f"  national file failed ({e}); using per-state files")
    frames = []
    for st in STATES:
        try:
            p = download(f"{BASE}/{st}-precincts-with-results.geojson.gz",
                         RAW / "elections" / f"{st}_precincts_2024.geojson.gz", retries=1)
            frames.append(gpd.read_file(f"/vsigzip/{p}"))
        except SystemExit:
            print(f"  {st}: no precinct file (NYT marks some states unusable)")
    return pd.concat(frames, ignore_index=True)


def main():
    print("NYT 2024 precinct results")
    gdf = load_precincts()
    gdf = gdf[[c for c in COLS if c in gdf.columns] + ["geometry"]]
    for c in ["votes_dem", "votes_rep", "votes_total"]:
        gdf[c] = pd.to_numeric(gdf[c], errors="coerce")
    gdf = gdf[gdf["votes_total"] > 0]
    gdf["county_fips"] = gdf["GEOID"].str[:5]
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    # Precinct table (no geometry) for drill-down and checks
    tab = gdf.drop(columns="geometry").rename(columns={"GEOID": "precinct_id"})
    tab["pct_dem"] = tab["votes_dem"] / tab["votes_total"]
    tab["pct_rep"] = tab["votes_rep"] / tab["votes_total"]
    tab["election_year"] = 2024
    save(tab, "elections_precinct")

    # Roll up to ZIP: each precinct counts toward the ZIP holding its interior point
    pts = gdf.copy()
    pts["geometry"] = gdf.to_crs("EPSG:5070").representative_point().to_crs(gdf.crs)
    zcta = gpd.read_parquet(PROCESSED / "geo_zcta.parquet")[["zcta", "geometry"]].to_crs(gdf.crs)
    j = gpd.sjoin(pts, zcta, how="inner", predicate="within")
    g = j.groupby("zcta")
    z = pd.DataFrame({
        "zip_votes_dem": g["votes_dem"].sum(),
        "zip_votes_rep": g["votes_rep"].sum(),
        "zip_votes_total": g["votes_total"].sum(),
        "zip_precincts": g.size(),
        "zip_share_official_boundary": g["official_boundary"].mean() if "official_boundary" in j else pd.NA,
    }).reset_index()
    z["zip_pct_dem"] = z["zip_votes_dem"] / z["zip_votes_total"]
    z["zip_pct_rep"] = z["zip_votes_rep"] / z["zip_votes_total"]
    z["zip_margin_dem_minus_rep"] = z["zip_pct_dem"] - z["zip_pct_rep"]
    z["election_year"] = 2024
    print(f"  precincts matched to a ZIP: {len(j):,} of {len(gdf):,}")
    save(z, "elections_zip")


if __name__ == "__main__":
    main()
