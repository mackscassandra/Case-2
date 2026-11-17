"""Census boundary files -> metro (CBSA), county and ZIP (ZCTA) tables.

Every other dataset joins to these keys:
  cbsa_code (5 digits), county_fips (5 digits), zcta (5 digits).
ZCTAs are assigned to the county and metro that contains their interior point,
which avoids crosswalk mismatches (e.g. Connecticut's 2022 county changes).
No API key needed.
"""
import geopandas as gpd

from common import PROCESSED, RAW, download, unzip

BASE = "https://www2.census.gov/geo/tiger"
FILES = {
    "cbsa": f"{BASE}/GENZ2023/shp/cb_2023_us_cbsa_500k.zip",
    "county": f"{BASE}/GENZ2023/shp/cb_2023_us_county_500k.zip",
    "zcta": f"{BASE}/GENZ2020/shp/cb_2020_us_zcta520_500k.zip",
}
EQUAL_AREA = "EPSG:5070"  # CONUS Albers, for areas and simplification
SQM_PER_SQMI = 2_589_988.11


def read(name: str) -> gpd.GeoDataFrame:
    z = download(FILES[name], RAW / "geo" / FILES[name].rsplit("/", 1)[1])
    return gpd.read_file(unzip(z))


def simplify(gdf: gpd.GeoDataFrame, tol_m: float) -> gpd.GeoDataFrame:
    out = gdf.to_crs(EQUAL_AREA)
    out["geometry"] = out.geometry.simplify(tol_m, preserve_topology=True)
    return out.to_crs("EPSG:4326")


def main():
    print("Metros (CBSA)")
    cbsa = read("cbsa").rename(columns={"GEOID": "cbsa_code", "NAME": "cbsa_name"})
    cbsa["is_metro"] = cbsa["LSAD"].eq("M1")  # M1 = metropolitan, M2 = micropolitan
    cbsa = cbsa[["cbsa_code", "cbsa_name", "is_metro", "geometry"]]

    print("Counties")
    county = read("county").rename(columns={"GEOID": "county_fips", "NAMELSAD": "county_name",
                                            "STUSPS": "state", "STATE_NAME": "state_name"})
    county = county[["county_fips", "county_name", "state", "state_name", "geometry"]]

    print("ZIP code tabulation areas (ZCTA)")
    zcta = read("zcta").rename(columns={"ZCTA5CE20": "zcta"})
    zcta["land_sqmi"] = zcta["ALAND20"] / SQM_PER_SQMI
    pts = zcta[["zcta", "geometry"]].copy()
    pts["geometry"] = zcta.to_crs(EQUAL_AREA).representative_point().to_crs(zcta.crs)
    pts = pts.to_crs(county.crs)
    pts["lon"], pts["lat"] = pts.geometry.x, pts.geometry.y
    pts = gpd.sjoin(pts, county[["county_fips", "state", "geometry"]], how="left", predicate="within").drop(columns="index_right")
    pts = gpd.sjoin(pts, cbsa[["cbsa_code", "geometry"]], how="left", predicate="within").drop(columns="index_right")
    pts = pts.drop_duplicates("zcta")
    zcta = zcta[["zcta", "land_sqmi", "geometry"]].merge(pts.drop(columns="geometry"), on="zcta", how="left")
    print(f"  ZCTAs without a county match: {zcta['county_fips'].isna().sum()} (territories/offshore)")

    # Simplified shapes keep the files small enough for GitHub and a fast web map.
    simplify(cbsa, 500).to_parquet(PROCESSED / "geo_cbsa.parquet", index=False)
    simplify(county, 300).to_parquet(PROCESSED / "geo_county.parquet", index=False)
    simplify(zcta, 100).to_parquet(PROCESSED / "geo_zcta.parquet", index=False)
    print(f"  saved geo_cbsa ({len(cbsa):,}), geo_county ({len(county):,}), geo_zcta ({len(zcta):,})")


if __name__ == "__main__":
    main()
