from census import CensusClient

c = CensusClient()
# ACS 5-Year: total population (B01003_001E) by state
for row in c.query("2022/acs/acs5", ["NAME", "B01003_001E"], {"for": "state:*"})[:10]:
    print(row["NAME"], row["B01003_001E"])
