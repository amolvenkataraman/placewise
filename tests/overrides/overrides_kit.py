"""Public places, hand-built lookup Results and small helpers for the overrides tests.

Every Result here is built by hand from public places, so no packs are needed.
"""

import importlib.util
import json

import pytest

from placewise.model import Layer, Nearby, Place, Result
from placewise.overrides import OverrideEngine

HAS_TOML = any(importlib.util.find_spec(name) for name in ("tomllib", "tomli"))
needs_toml = pytest.mark.skipif(not HAS_TOML, reason="needs tomllib (3.11+) or tomli")

# --- public places -----------------------------------------------------------------------------

CANADA = Place("wikidata:Q16", "Canada", "country", codes={"iso2": "CA"})
ONTARIO = Place("wikidata:Q1904", "Ontario", "admin1", codes={"iso2": "CA-ON"})
PEEL = Place("statcan:cd:3521", "Peel", "admin2", codes={"ca_cd": "3521"})
TORONTO_DIV = Place("statcan:cd:3520", "Toronto", "admin2", codes={"ca_cd": "3520"})
MISSISSAUGA = Place("wikidata:Q50816", "Mississauga", "locality")
TORONTO = Place("wikidata:Q172", "Toronto", "locality")
KARIYA_PARK = Place("osm:way/kariya-park", "Kariya Park", "park", tier=3)
LAKE_ONTARIO = Place("wikidata:Q1062", "Lake Ontario", "water")
RATTRAY_MARSH = Place("osm:way/rattray-marsh", "Rattray Marsh", "park", tier=3)
PEARSON = Place("wikidata:Q29415", "Toronto Pearson International Airport", "airport", codes={"iata": "YYZ"})

USA = Place("wikidata:Q30", "United States", "country", codes={"iso2": "US"})
CALIFORNIA = Place("wikidata:Q99", "California", "admin1", codes={"iso2": "US-CA"})
ALAMEDA = Place("wikidata:Q107146", "Alameda County", "admin2")
OAKLAND = Place("wikidata:Q17042", "Oakland", "locality")
SAN_FRANCISCO = Place("wikidata:Q62", "San Francisco", "locality")
DATA_BAY_AREA = Place("wikidata:Q213205", "San Francisco Bay Area", "region")

MISSISSAUGA_PT = (43.5890, -79.6441)  # Mississauga Civic Centre
TORONTO_PT = (43.6532, -79.3832)  # Toronto City Hall
OAKLAND_PT = (37.8053, -122.2725)  # Oakland City Hall
SF_PT = (37.7793, -122.4193)  # San Francisco City Hall

GTA_MEMBERS = {"ca_cd": ["3518", "3519", "3520", "3521", "3524"]}


def mississauga_result():
    return Result(
        *MISSISSAUGA_PT,
        label="Mississauga, Ontario",
        country=CANADA,
        admin1=ONTARIO,
        admin2=PEEL,
        city=MISSISSAUGA,
        locality=MISSISSAUGA,
        within=(KARIYA_PARK,),
        near=(Nearby(LAKE_ONTARIO, "near", 4.0), Nearby(RATTRAY_MARSH, "near", 6.0)),
        airport=Nearby(PEARSON, "near", 7.0),
        sources={"locality": "data:ca-2026.11"},
    )


def toronto_result():
    return Result(
        *TORONTO_PT,
        label="Toronto, Ontario",
        country=CANADA,
        admin1=ONTARIO,
        admin2=TORONTO_DIV,
        city=TORONTO,
        locality=TORONTO,
    )


def oakland_result():
    return Result(
        *OAKLAND_PT,
        label="Oakland, California",
        country=USA,
        admin1=CALIFORNIA,
        admin2=ALAMEDA,
        city=OAKLAND,
        locality=OAKLAND,
        regions=(DATA_BAY_AREA,),
    )


def sf_result():
    return Result(
        *SF_PT,
        label="San Francisco, California",
        country=USA,
        admin1=CALIFORNIA,
        city=SAN_FRANCISCO,
        locality=SAN_FRANCISCO,
    )


def engine(**layers):
    """An engine from in-memory documents: engine(repo={...}, app={...}, local={...})."""
    return OverrideEngine.from_documents(
        [(Layer(name), doc, f"{name}:{name}.toml") for name, doc in layers.items()]
    )


def apply(eng, result):
    return eng.apply(result, result.lat, result.lon)


def write(path, doc):
    path.write_text(json.dumps(doc))
    return path
