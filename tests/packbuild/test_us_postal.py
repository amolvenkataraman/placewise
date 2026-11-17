# ruff: noqa: E501  (data rows are longer than a line)
"""ZIP Code postal city names: ZIP Code Business Patterns (public domain) first, GeoNames postal
codes (CC BY 4.0) for ZIP Codes it lacks, each matched to the census place it names."""

import pytest

from packbuild.sources.usa import postal

# zbp23totals.txt rows (quoted CSV, upper case city names)
ZBP = """\
"zip","name","emp_nf","emp","qp1_nf","qp1","ap_nf","ap","est","city","stabbr","cty_name"
"89109","LAS VEGAS, NV","G",150000,"G",1,"G",1,900,"LAS VEGAS","NV","CLARK"
"90022","LOS ANGELES, CA","G",9000,"G",1,"G",1,800,"LOS ANGELES","CA","LOS ANGELES"
"22102","MC LEAN, VA","G",90000,"G",1,"G",1,2000,"MC LEAN","VA","FAIRFAX"
"11201","BROOKLYN, NY","G",60000,"G",1,"G",1,3000,"BROOKLYN","NY","KINGS"
"27101","WINSTON SALEM, NC","G",30000,"G",1,"G",1,1500,"WINSTON SALEM","NC","FORSYTH"
"92509","JURUPA VALLEY, CA","G",20000,"G",1,"G",1,1200,"JURUPA VALLEY","CA","RIVERSIDE"
"63101","SAINT LOUIS, MO","G",50000,"G",1,"G",1,1600,"SAINT LOUIS","MO","ST. LOUIS CITY"
"""
# US.txt rows (tab-separated): country, ZIP, place name, state, state code, county, ...
GEONAMES = (
    "US\t89109\tLas Vegas\tNevada\tNV\tClark\t003\t\t\t36.1251\t-115.1693\t4\n"
    "US\t27101\tWinston-Salem\tNorth Carolina\tNC\tForsyth\t067\t\t\t36.0999\t-80.2442\t4\n"
    "US\t92509\tRiverside\tCalifornia\tCA\tRiverside\t065\t\t\t33.999\t-117.4462\t4\n"
    "US\t95389\tYosemite National Park\tCalifornia\tCA\tMariposa\t043\t\t\t37.7156\t-119.6763\t4\n"
    "US\t77380\tSpring\tTexas\tTX\tMontgomery\t339\t\t\t30.1442\t-95.4685\t4\n"
)
# tab20_zcta520_place20_natl.txt: pipe-separated with a byte-order mark; place parts outside
# every ZCTA have an empty ZCTA
HEAD = (
    "﻿OID_ZCTA5_20|GEOID_ZCTA5_20|NAMELSAD_ZCTA5_20|AREALAND_ZCTA5_20|AREAWATER_ZCTA5_20|MTFCC_ZCTA5_20|"
    "CLASSFP_ZCTA5_20|FUNCSTAT_ZCTA5_20|OID_PLACE_20|GEOID_PLACE_20|NAMELSAD_PLACE_20|AREALAND_PLACE_20|"
    "AREAWATER_PLACE_20|MTFCC_PLACE_20|CLASSFP_PLACE_20|FUNCSTAT_PLACE_20|AREALAND_PART|AREAWATER_PART\n"
)
REL = HEAD + (
    "||||||||27890103022968|0101852|Anniston city|118685613|180468|G4110|C1|A|9974104|35266\n"
    "1|89109|ZCTA5 89109|10683404|0|G6350|B5|S|2|3240000|Las Vegas city|367325845|138524|G4110|C1|A|450178|0\n"
    "1|89109|ZCTA5 89109|10683404|0|G6350|B5|S|3|3254600|Paradise CDP|109826212|0|G4210|U1|S|5240050|0\n"
    "1|77380|ZCTA5 77380|1|0|G6350|B5|S|4|4872656|The Woodlands CDP|1|0|G4210|U1|S|1|0\n"
    "1|90022|ZCTA5 90022|1|0|G6350|B5|S|5|0620802|East Los Angeles CDP|1|0|G4210|U1|S|1|0\n"
)
# (GEOID, name, state, incorporated, population): the census places
PLACES = [
    ("3240000", "Las Vegas", "NV", True, 679817),
    ("3254600", "Paradise", "NV", False, 185913),
    ("0644000", "Los Angeles", "CA", True, 3857263),
    ("0620802", "East Los Angeles", "CA", False, 111647),
    ("5148376", "McLean", "VA", False, 50773),
    ("3775000", "Winston-Salem", "NC", True, 255769),
    ("0637692", "Jurupa Valley", "CA", True, 107000),
    ("2965000", "St. Louis", "MO", True, 279695),
    ("4869596", "Spring", "TX", False, 62559),
    ("4872656", "The Woodlands", "TX", False, 121002),
    # two places of one name in a state: the one overlapping the ZCTA wins
    ("4800001", "Spring", "TX", False, 10),
]


@pytest.fixture
def files(tmp_path):
    zbp = tmp_path / "zbp23totals.txt"
    zbp.write_text(ZBP, encoding="utf-8")
    gn = tmp_path / "US.txt"
    gn.write_text(GEONAMES, encoding="utf-8")
    rel = tmp_path / "tab20_zcta520_place20_natl.txt"
    rel.write_text(REL, encoding="utf-8")
    return zbp, gn, rel


def test_readers(files):
    zbp, gn, rel = files
    assert postal.read_zbp(zbp)["22102"] == ("MC LEAN", "VA")
    assert postal.read_geonames_postal(gn)["27101"] == ("Winston-Salem", "NC")
    overlaps = postal.read_zcta_places(rel)
    assert overlaps == {"89109": ["3240000", "3254600"], "77380": ["4872656"], "90022": ["0620802"]}


@pytest.mark.parametrize(
    ("name", "key"),
    [("Mc Lean", "mclean"), ("WINSTON SALEM", "winstonsalem"), ("Saint Louis", "stlouis"),
     ("St. Louis", "stlouis"), ("Coeur D Alene", "coeurdalene"), ("Mount Vernon", "mtvernon"),
     ("Española", "espanola")],
)  # fmt: skip
def test_name_key_ignores_spacing_punctuation_and_saint(name, key):
    assert postal.name_key(name) == key


def test_postal_cities(files):
    zbp, gn, rel = files
    zctas = ["89109", "90022", "22102", "11201", "27101", "92509", "63101", "95389", "77380", "00000"]
    found = postal.postal_cities(
        zctas, postal.read_zbp(zbp), postal.read_geonames_postal(gn), PLACES, postal.read_zcta_places(rel)
    )
    assert found["89109"] == {"city": "Las Vegas", "place": "3240000", "source": "zbp"}
    assert found["90022"] == {"city": "Los Angeles", "place": "0644000", "source": "zbp"}  # no overlap needed
    assert found["22102"] == {"city": "McLean", "place": "5148376", "source": "zbp"}  # the place's spelling
    assert found["11201"] == {"city": "Brooklyn", "place": "", "source": "zbp"}  # no such place: title case
    assert found["27101"]["city"] == "Winston-Salem"
    # Business Patterns is the newer name (Jurupa Valley incorporated in 2011); GeoNames still says Riverside
    assert found["92509"] == {"city": "Jurupa Valley", "place": "0637692", "source": "zbp"}
    assert found["63101"] == {"city": "St. Louis", "place": "2965000", "source": "zbp"}
    # ZIP Codes Business Patterns lacks come from GeoNames
    assert found["95389"] == {"city": "Yosemite National Park", "place": "", "source": "geonames"}
    assert found["77380"] == {"city": "Spring", "place": "4869596", "source": "geonames"}
    assert found["00000"] == {"city": "", "place": "", "source": ""}


def test_a_same_named_place_overlapping_the_zcta_wins(files):
    gn = files[1]
    overlaps = {"77380": ["4800001"]}
    found = postal.postal_cities(["77380"], {}, postal.read_geonames_postal(gn), PLACES, overlaps)
    assert found["77380"]["place"] == "4800001"


def test_title_case():
    assert postal.title_case("LAS VEGAS") == "Las Vegas"
    assert postal.title_case("MC LEAN") == "Mc Lean"
    assert postal.title_case("") == ""
