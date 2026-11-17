# ruff: noqa: E501  (rows copied from the real files are longer than a line)
"""The US pack's naming inputs beside us_fixtures' boundaries: ACS B01003, OMB list 2, ZIP Code
Business Patterns, GeoNames US postal codes and the ZCTA-to-place relationship file, cut to the
fixture places (Paradise, San Francisco, Oakland, Las Vegas, Reno) and ZCTAs (89109, 94117,
95389). Values are copied from the real files."""

from pathlib import Path

from us_fixtures import write_xlsx

ACS = """\
GEO_ID|B01003_E001|B01003_M001
0100000US|334922499|-555555555
1600000US0653000|436504|-555555555
1600000US0667000|836321|-555555555
1600000US3240000|660400|126
1600000US3254600|185913|4513
1600000US3260600|273448|103
860Z200US89109|6504|1081
860Z200US94117|45452|1690
860Z200US95389|1093|283
"""

LIST2_HEADER = ("CBSA Code", "CBSA Title", "Metropolitan/Micropolitan Statistical Area", "Principal City Name",
                "FIPS State Code", "FIPS Place Code")  # fmt: skip
LIST2_ROWS = [
    ("29820", "Las Vegas-Henderson-North Las Vegas, NV", "Metropolitan Statistical Area", "Henderson", "32", "31900"),
    ("29820", "Las Vegas-Henderson-North Las Vegas, NV", "Metropolitan Statistical Area", "Las Vegas", "32", "40000"),
    ("29820", "Las Vegas-Henderson-North Las Vegas, NV", "Metropolitan Statistical Area", "Paradise", "32", "54600"),
    ("39900", "Reno, NV", "Metropolitan Statistical Area", "Reno", "32", "60600"),
    ("41860", "San Francisco-Oakland-Fremont, CA", "Metropolitan Statistical Area", "Berkeley", "06", "06000"),
    ("41860", "San Francisco-Oakland-Fremont, CA", "Metropolitan Statistical Area", "Oakland", "06", "53000"),
    ("41860", "San Francisco-Oakland-Fremont, CA", "Metropolitan Statistical Area", "San Francisco", "06", "67000"),
]  # fmt: skip

ZBP = """\
"zip","name","emp_nf","emp","qp1_nf","qp1","ap_nf","ap","est","city","stabbr","cty_name"
"89109","LAS VEGAS, NV","G",150000,"G",1,"G",1,900,"LAS VEGAS","NV","CLARK"
"94117","SAN FRANCISCO, CA","G",9000,"G",1,"G",1,800,"SAN FRANCISCO","CA","SAN FRANCISCO"
"""
GEONAMES = (
    "US\t89109\tLas Vegas\tNevada\tNV\tClark\t003\t\t\t36.1251\t-115.1693\t4\n"
    "US\t95389\tYosemite National Park\tCalifornia\tCA\tMariposa\t043\t\t\t37.7156\t-119.6763\t4\n"
)
RELATIONSHIP = (
    "﻿OID_ZCTA5_20|GEOID_ZCTA5_20|NAMELSAD_ZCTA5_20|AREALAND_ZCTA5_20|AREAWATER_ZCTA5_20|MTFCC_ZCTA5_20|"
    "CLASSFP_ZCTA5_20|FUNCSTAT_ZCTA5_20|OID_PLACE_20|GEOID_PLACE_20|NAMELSAD_PLACE_20|AREALAND_PLACE_20|"
    "AREAWATER_PLACE_20|MTFCC_PLACE_20|CLASSFP_PLACE_20|FUNCSTAT_PLACE_20|AREALAND_PART|AREAWATER_PART\n"
    "221704258469986|89109|ZCTA5 89109|10683404|0|G6350|B5|S|27890679599946|3240000|Las Vegas city|367325845|138524|G4110|C1|A|450178|0\n"
    "221704258469986|89109|ZCTA5 89109|10683404|0|G6350|B5|S|28090679599936|3254600|Paradise CDP|109826212|0|G4210|U1|S|5240050|0\n"
    "221704258460000|94117|ZCTA5 94117|3301059|0|G6350|B5|S|27890679590000|0667000|San Francisco city|121485107|479107241|G4110|C1|A|3301059|0\n"
)


def write(folder):
    """{registry download name: path} for the naming inputs."""
    folder = Path(folder)
    acs = folder / "acsdt5y2024-b01003.dat"
    acs.write_text(ACS, encoding="utf-8")
    list2 = write_xlsx(
        folder / "list2_2023.xlsx",
        [("Table with row headers in column A and column headers in row 3",),
         ("List 2. PRINCIPAL CITIES OF METROPOLITAN AND MICROPOLITAN STATISTICAL AREAS, JULY 2023",),
         LIST2_HEADER, *LIST2_ROWS, (), ("Note: OMB's 2020 Standards ...",)],
    )  # fmt: skip
    zbp = folder / "zbp23totals.txt"
    zbp.write_text(ZBP, encoding="utf-8")
    geonames = folder / "US.txt"
    geonames.write_text(GEONAMES, encoding="utf-8")
    relationship = folder / "tab20_zcta520_place20_natl.txt"
    relationship.write_text(RELATIONSHIP, encoding="utf-8")
    return {
        "acs_population": acs,
        "principal_cities": list2,
        "zip_cities": zbp,
        "zcta_place": relationship,
        "postal_us": geonames,
    }
