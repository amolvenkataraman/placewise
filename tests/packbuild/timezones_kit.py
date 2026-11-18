"""Small polygon layers and curated time-zone tables for the pack build tests."""

from packbuild import timezones
from placewise.model import Feature, Outline
from placewise.packs import LayerData


def box(south, west, north, east):
    """A box Feature (lat, lon rings, counter-clockwise)."""
    ring = ((south, west), (south, east), (north, east), (north, west))
    return Feature(outlines=(Outline((ring,)),))


def polygon_layer(name, units):
    """A LayerData from (id, name, {column: value}, Feature) rows."""
    columns = {"id": [u[0] for u in units], "name": [u[1] for u in units]}
    for field in units[0][2] if units else ():
        columns[field] = [u[2][field] for u in units]
    features = [Feature(u[3].outlines, {}, u[0]) for u in units]
    return LayerData(name, "polygon", columns, ("synthetic",), features=features)


SOURCES = {
    "tzdb": {"title": "tz database", "url": "https://data.iana.org/time-zones/", "licence": "public domain"}
}

# for the tiny fixtures' units (not the dataset's, whose units the fixtures don't have)
TABLES = {
    "world": {
        "sources": SOURCES,
        "countries": {"iso:CA": "America/Toronto", "iso:IN": "Asia/Kolkata", "ne:SOL": "Africa/Mogadishu"},
        "shapes": [
            {
                "id": "tz:test-box",
                "zone": "America/Winnipeg",
                "within": "iso:CA",
                "boxes": [[50, -98, 51, -97]],
            }
        ],
    },
    "usa": {
        "country": "US",
        "sources": SOURCES,
        "admin1": {
            "iso:US-NV": {
                "zone": "America/Los_Angeles",
                "parts": {"census:32031": ["America/Los_Angeles", "America/Denver"]},
            },
            "iso:US-CA": "America/Los_Angeles",
            "iso:US-GU": "Pacific/Guam",
        },
        "shapes": [{"id": "tz:test-reservation", "zone": "America/Denver", "aiannh": "9001"}],
    },
    "can": {
        "country": "CA",
        "sources": SOURCES,
        "admin1": {
            "statcan:35": {
                "zone": "America/Toronto",
                "parts": {"statcan:3524": "America/Winnipeg", "statcan:3524009": "America/Atikokan"},
            },
            "statcan:24": "America/Toronto",
            "statcan:48": "America/Edmonton",
        },
        "shapes": [],
    },
}


def use_timezones(monkeypatch, tables=TABLES):
    """Make the builders read `tables` ({"world": doc, "usa": doc ...}) instead of datasets/timezones."""
    monkeypatch.setattr(timezones, "load", lambda name, folder=None: tables[name])
