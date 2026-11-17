# ruff: noqa: E501  (data rows are longer than a line)
"""A synthetic world and country packs for the naming tests: invented boxes in open Pacific water
that carry the real packs' layer names, columns and id schemes (packbuild/README.md). The ISO
codes are real so the rules recognise the countries; every place and coordinate is made up.

      lon -150 ........ -149.5 .. -149.4 ... -149 | -149 ......... -148 | -148 ........ -147
lat 11  "US" (us pack)                            | "CA" (ca pack)       | "IN" (in pack)
        Kings County / New York city   (gap)  San | Toronto | King TP / | HR pin | KA pin
lat 10.5 ---------------------------------- Mateo |---------| Banff ID  |--------+--------
        Clark County: Las Vegas, Paradise,     Co.| Peel    | Niagara   | DL pin | OD pin
lat 10  Henderson                                 |         |           |        |
"""

import numpy as np

from placewise.model import Feature, Outline
from placewise.packs import LayerData, write_pack

CREATED = "2026-11-17T00:00:00Z"
VERSION = "2026.11"


def box(south, west, north, east):
    ring = ((south, west), (south, east), (north, east), (north, west))
    return Feature(outlines=(Outline((ring,)),))


def polygons(name, rows, columns, source="synthetic"):
    """A polygon layer from rows of (box, value per column); population is i8 with null -1, as in
    the real packs."""
    data = {c: [r[1 + i] for r in rows] for i, c in enumerate(columns)}
    types, nulls = ({"population": "i8"}, {"population": -1}) if "population" in data else ({}, {})
    return LayerData(
        name, "polygon", data, (source,), features=[box(*r[0]) for r in rows], types=types, nulls=nulls
    )


# -- world ---------------------------------------------------------------------------------------

COUNTRIES = [
    ((10, -150, 11, -149), "iso:US", "United States of America", "US", "USA"),
    ((10, -149, 11, -148), "iso:CA", "Canada", "CA", "CAN"),
    ((10, -148, 11, -147), "iso:IN", "India", "IN", "IND"),
]
ADMIN1 = [
    ((10, -150, 10.5, -149.5), "iso:US-NV", "Nevada", "US", "USA"),
    ((10.5, -150, 11, -149.5), "iso:US-NY", "New York", "US", "USA"),
    ((10, -149.5, 11, -149), "iso:US-CA", "California", "US", "USA"),
    ((10, -149, 11, -148), "iso:CA-ON", "Ontario", "CA", "CAN"),
    ((10, -148, 10.5, -147.5), "iso:IN-DL", "Delhi", "IN", "IND"),
    ((10.5, -148, 11, -147.5), "iso:IN-HR", "Haryana", "IN", "IND"),
    ((10, -147.5, 10.5, -147), "iso:IN-OR", "Odisha", "IN", "IND"),  # Natural Earth keeps the old code
    ((10.5, -147.5, 11, -147), "iso:IN-KA", "Karnataka", "IN", "IND"),
]
CITIES = [
    # id, name, lat, lon, country, population, feature_code, timezone
    ("geonames:101", "Las Vegas", 10.42, -149.9, "US", 640_000, "PPLA2", "America/Los_Angeles"),
    ("geonames:102", "Paradise", 10.15, -149.9, "US", 223_000, "PPL", "America/Los_Angeles"),
    ("geonames:103", "New York City", 10.75, -149.76, "US", 8_800_000, "PPL", "America/New_York"),
    ("geonames:104", "Williamsfield", 10.70, -149.80, "US", 33_000, "PPLX", "America/New_York"),
    ("geonames:105", "Emeryville", 10.52, -149.27, "US", 12_000, "PPL", "America/Los_Angeles"),
    ("geonames:106", "Oakland", 10.53, -149.33, "US", 419_000, "PPLA2", "America/Los_Angeles"),
    ("geonames:107", "Mission Quarter", 10.70, -149.20, "US", 47_000, "PPLX", "America/Los_Angeles"),
    ("geonames:108", "Farview", 10.20, -149.05, "US", 2_000, "PPL", "America/Los_Angeles"),
    ("geonames:109", "Brooklyn", 10.60, -149.90, "US", 2_700_000, "PPLA2", "America/New_York"),
    ("geonames:201", "Etobicoke", 10.55, -148.80, "CA", 365_000, "PPL", "America/Toronto"),
    ("geonames:202", "Eringate", 10.51, -148.80, "CA", 18_000, "PPLX", "America/Toronto"),
    ("geonames:203", "Rouge", 10.90, -148.60, "CA", 46_000, "PPLX", "America/Toronto"),
    ("geonames:204", "Fieldbrook", 10.60, -148.30, "CA", 1_000, "PPL", "America/Toronto"),
    ("geonames:205", "King City", 10.85, -148.30, "CA", 2_700, "PPL", "America/Toronto"),
    ("geonames:206", "Toronto", 10.75, -148.75, "CA", 2_600_000, "PPLA", "America/Toronto"),
    ("geonames:301", "Gurugram", 10.55, -147.80, "IN", 886_519, "PPLA2", "Asia/Kolkata"),
    ("geonames:302", "Kapas Hera", 10.43, -147.80, "IN", 74_073, "PPL", "Asia/Kolkata"),
    ("geonames:303", "Delhi", 10.20, -147.80, "IN", 11_000_000, "PPLA", "Asia/Kolkata"),
    ("geonames:304", "Bengaluru", 10.75, -147.25, "IN", 8_400_000, "PPLA", "Asia/Kolkata"),
]


def write_world(out):
    countries = LayerData(
        "countries", "polygon",
        {"id": [c[1] for c in COUNTRIES], "name": [c[2] for c in COUNTRIES],
         "iso2": [c[3] for c in COUNTRIES], "iso3": [c[4] for c in COUNTRIES],
         "adm0_a3": [c[4] for c in COUNTRIES], "sovereign": [c[2] for c in COUNTRIES]},
        ("synthetic",), features=[box(*c[0]) for c in COUNTRIES],
    )  # fmt: skip
    admin1 = LayerData(
        "admin1", "polygon",
        {"id": [a[1] for a in ADMIN1], "name": [a[2] for a in ADMIN1], "country": [a[3] for a in ADMIN1],
         "adm0_a3": [a[4] for a in ADMIN1]},
        ("synthetic",), features=[box(*a[0]) for a in ADMIN1],
    )  # fmt: skip
    cities = LayerData(
        "cities", "point",
        {"id": [c[0] for c in CITIES], "name": [c[1] for c in CITIES], "country": [c[4] for c in CITIES],
         "population": np.array([c[5] for c in CITIES], dtype=np.int64),
         "feature_code": [c[6] for c in CITIES], "timezone": [c[7] for c in CITIES]},
        ("synthetic",), lat=np.array([c[2] for c in CITIES]), lon=np.array([c[3] for c in CITIES]),
    )  # fmt: skip
    return write_pack(out / "world", "world", VERSION, [countries, admin1, cities], created=CREATED)


# -- United States -------------------------------------------------------------------------------

CLARK, KINGS, SAN_MATEO = (10, -150, 10.5, -149.4), (10.5, -150, 11, -149.5), (10, -149.4, 11, -149)
US_COUNTIES = [
    (CLARK, "census:32003", "Clark County", "NV", "29820", "332"),
    (KINGS, "census:36047", "Kings County", "NY", "35620", "408"),  # a gap of water east of it
    (SAN_MATEO, "census:06081", "San Mateo County", "CA", "41860", "488"),
]
US_PLACES = [
    # box, id, name, class, state, population, intpt_lat, intpt_lon
    ((10.3, -150, 10.5, -149.8), "census:3240000", "Las Vegas", "incorporated", "NV", 650_000, 10.4, -149.9),
    ((10.0, -150, 10.3, -149.8), "census:3254600", "Paradise", "cdp", "NV", 185_000, 10.15, -149.9),
    ((10.0, -149.7, 10.2, -149.5), "census:3231900", "Henderson", "incorporated", "NV", 330_000, 10.1, -149.6),
    ((10.0, -149.45, 10.1, -149.4), "census:3240600", "Laughlin", "cdp", "NV", 8_000, 10.05, -149.42),
    # a CDP named after its postal city (like East Los Angeles); a big and a small CDP whose ZIP
    # Code says Paradise (another CDP)
    ((10.3, -149.8, 10.45, -149.7), "census:3299901", "East Las Vegas", "cdp", "NV", 110_000, 10.4, -149.75),
    ((10.1, -149.8, 10.2, -149.7), "census:3284600", "Winchester", "cdp", "NV", 36_000, 10.15, -149.75),
    ((10.0, -149.8, 10.1, -149.7), "census:3206500", "Blue Diamond", "cdp", "NV", 290, 10.05, -149.75),
    (KINGS, "census:3651000", "New York", "incorporated", "NY", 8_500_000, 10.75, -149.75),
    ((10.5, -149.3, 10.55, -149.25), "census:0622594", "Emeryville", "incorporated", "CA", 13_000, 10.52, -149.27),
    ((10.6, -149.3, 10.9, -149.1), "census:0667000", "San Francisco", "incorporated", "CA", 826_000, 10.75, -149.2),
]  # fmt: skip
US_ZCTA = [
    # box, id, name, postal_city, postal_place
    ((10.22, -150, 10.3, -149.8), "census:zcta:89109", "89109", "Las Vegas", "census:3240000"),
    ((10.3, -149.8, 10.45, -149.7), "census:zcta:89110", "89110", "Las Vegas", "census:3240000"),
    ((10.0, -149.8, 10.2, -149.7), "census:zcta:89118", "89118", "Paradise", "census:3254600"),
    # Laughlin's ZIP Code names a city 35 km off: too far to stand for it
    ((10.0, -149.45, 10.1, -149.4), "census:zcta:89029", "89029", "Las Vegas", "census:3240000"),
    ((10.5, -149.25, 10.6, -149.1), "census:zcta:94128", "94128", "San Francisco", "census:0667000"),
    ((10.6, -149.3, 10.9, -149.1), "census:zcta:94103", "94103", "San Francisco", "census:0667000"),
    ((10.5, -150, 11, -149.5), "census:zcta:11211", "11211", "Brooklyn", ""),  # no census place of that name
]
US_CBSA = [
    (CLARK, "census:cbsa:29820", "Las Vegas-Henderson-North Las Vegas, NV Metro Area",
     "Las Vegas-Henderson-North Las Vegas, NV", "29820", "metro", "census:3240000,census:3231900,census:3254600"),
    (KINGS, "census:cbsa:35620", "New York-Newark-Jersey City, NY-NJ Metro Area",
     "New York-Newark-Jersey City, NY-NJ", "35620", "metro", "census:3651000"),
    (SAN_MATEO, "census:cbsa:41860", "San Francisco-Oakland-Fremont, CA Metro Area",
     "San Francisco-Oakland-Fremont, CA", "41860", "metro", "census:0667000"),
]  # fmt: skip
US_CSA = [(CLARK, "census:csa:332", "Las Vegas-Henderson, NV CSA", "Las Vegas-Henderson, NV", "332")]


def write_us(out, regions=None):
    counties = polygons("counties", US_COUNTIES, ("id", "name", "state", "cbsa", "csa"), "uscensus")
    places = polygons(
        "places",
        US_PLACES,
        ("id", "name", "class", "state", "population", "intpt_lat", "intpt_lon"),
        "uscensus",
    )
    zcta = polygons("zcta", US_ZCTA, ("id", "name", "postal_city", "postal_place"), "uscensus")
    cbsa = polygons("cbsa", US_CBSA, ("id", "name", "title", "code", "type", "principal_cities"), "uscensus")
    csa = polygons("csa", US_CSA, ("id", "name", "title", "code"), "uscensus")
    layers = [counties, places, zcta, cbsa, csa, *([regions] if regions else [])]
    return write_pack(out / "us", "us", VERSION, layers, created=CREATED)


# -- Canada --------------------------------------------------------------------------------------

CA_CD = [
    ((10.5, -149, 11, -148.5), "statcan:3520", "Toronto", "CDR", "ON", 2_794_356),
    ((10, -149, 10.5, -148.5), "statcan:3521", "Peel", "RM", "ON", 1_451_022),
    ((10, -148.5, 10.5, -148), "statcan:3526", "Niagara", "RM", "ON", 477_941),
    ((10.5, -148.5, 11, -148), "statcan:4815", "Division No. 15", "CDR", "ON", 37_735),
    # a CSD's division comes from its CSDUID, not from these shapes: Pickering is in Durham
    ((10, -148.75, 10.5, -148.5), "statcan:3518", "Durham", "RM", "ON", 696_992),
    ((10.75, -148.5, 11, -148), "statcan:3519", "York", "RM", "ON", 1_173_334),
]
CA_CSD = [
    ((10.5, -149, 11, -148.5), "statcan:3520005", "Toronto", "C", "ON", 2_794_356),
    ((10, -149, 10.5, -148.75), "statcan:3521005", "Mississauga", "CY", "ON", 717_961),
    ((10, -148.75, 10.5, -148.5), "statcan:3518001", "Pickering", "CY", "ON", 99_186),
    ((10, -148.5, 10.25, -148), "statcan:3526003", "Fort Erie", "T", "ON", 32_901),
    ((10.25, -148.5, 10.5, -148.25), "statcan:3526057", "St. Catharines", "CY", "ON", 136_803),
    ((10.25, -148.25, 10.5, -148.02), "statcan:3526043", "Niagara Falls", "CY", "ON", 94_415),  # river east
    ((10.5, -148.5, 10.75, -148), "statcan:4815032", "Improvement District No. 9 Banff", "ID", "ON", 1_004),
    ((10.75, -148.5, 11, -148), "statcan:3519001", "King", "TP", "ON", 27_333),
]
CA_CMA = [
    ((10, -149, 11, -148.5), "statcan:35535", "Toronto", "CMA", "ON", 6_202_225),
    ((10, -148.5, 10.5, -148), "statcan:35539", "St. Catharines - Niagara", "CMA", "ON", 433_604),
]


CA_NAMED = [
    # id, name, generic, scale, lat, lon: CGNDB-like populated places
    ("cgndb:A1", "Lake Lucerne", "Hamlet", 1_200_000, 10.70, -148.10),  # in Banff ID
    ("cgndb:A2", "Scarbrook", "Community", 1_200_000, 10.80, -148.75),  # a former borough of Toronto
    ("cgndb:A3", "Toronto Junction", "Locality", 1_200_000, 10.83, -148.73),  # a locality: never named
    ("cgndb:A4", "Maltby", "Urban Community", 145_000, 10.45, -148.90),  # in Mississauga
    ("cgndb:A5", "Kettle", "Dispersed Rural Community", 250_000, 10.88, -148.20),  # in King TP
    ("cgndb:A6", "Toronto", "Community", 250_000, 10.70, -148.60),  # the locality's own name
]


def named_places(rows=CA_NAMED):
    return LayerData(
        "populated_places", "point",
        {"id": [r[0] for r in rows], "name": [r[1] for r in rows], "generic": [r[2] for r in rows],
         "province": ["ON"] * len(rows), "scale": np.array([r[3] for r in rows], dtype=np.int64)},
        ("synthetic",), lat=np.array([r[4] for r in rows]), lon=np.array([r[5] for r in rows]),
    )  # fmt: skip


def write_ca(out, regions=None):
    provinces = polygons(
        "provinces", [((10, -149, 11, -148), "statcan:35", "Ontario", "ON")], ("id", "name", "code")
    )
    cd = polygons("cd", CA_CD, ("id", "name", "cdtype", "province", "population"))
    csd = polygons("csd", CA_CSD, ("id", "name", "csdtype", "province", "population"))
    cma = polygons("cma", CA_CMA, ("id", "name", "kind", "province", "population"))
    fsa = polygons(
        "fsa", [((10, -149, 10.5, -148.75), "statcan:L4T", "L4T", "ON")], ("id", "name", "province")
    )
    layers = [provinces, cd, csd, cma, fsa, named_places(), *([regions] if regions else [])]
    return write_pack(out / "ca", "ca", VERSION, layers, created=CREATED)


# -- India ---------------------------------------------------------------------------------------

IN_PINCODES = [
    ((10.4, -148, 10.6, -147.5), "pin:122002", "DLF QE SO", "122002", "GURUGRAM", "IN-HR"),
    ((10, -148, 10.4, -147.5), "pin:110001", "New Delhi GPO", "110001", "NEW DELHI", "IN-DL"),
    ((10, -147.5, 10.5, -147), "pin:751001", "Bhubaneswar G.P.O.", "751001", "KHORDHA", "IN-OD"),
    ((10.5, -147.5, 11, -147), "pin:560066", "Whitefield S.O", "560066", "BENGALURU URBAN", "IN-KA"),
]


def write_in(out):
    pincodes = polygons("pincodes", IN_PINCODES, ("id", "name", "pincode", "district", "state_code"))
    return write_pack(out / "in", "in", VERSION, [pincodes], created=CREATED)


def regions_layer(rows):
    """A curated `regions` layer: rows of (box, id, name, kind, country)."""
    return polygons("regions", rows, ("id", "name", "kind", "country"), "synthetic-regions")


def write_all(out):
    return write_world(out), write_us(out), write_ca(out), write_in(out)
