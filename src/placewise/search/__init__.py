"""Forward search: a name in, places out, offline (docs/search.md).

    import placewise
    placewise.find("Yosemite")[0]                  # Entity: place, point inside, bbox, radius
    placewise.find("Paris", country="USA")[0]      # Paris, Texas
    placewise.find("Springfield, IL")              # context in the text
    placewise.find("YYZ")                          # Toronto (the city it serves), then the airport
    placewise.get("census:0646870")                # by placewise id
    placewise.outline("iso:US-CA", simplify_m=500) # its outline as GeoJSON
    placewise.suggest("Mississ")                   # type-ahead

Queries are read by `query`, candidates come from every open pack's name index (`gather`), are
ranked (`rank`) under the caller's context (`context`), merged across packs (`dedupe`) and built
into Entities with their city, region and country (`entities`); `engine.Search` runs it all.
`SearchGazetteer` plugs search into location search (placewise.text.parse_location).
"""

from .engine import Search
from .gazetteer import SearchGazetteer
from .query import Query, parse_query

__all__ = ["Query", "Search", "SearchGazetteer", "find", "get", "outline", "parse_query", "suggest"]


def _default():
    from placewise.engine import default_geocoder

    return default_geocoder()


def find(text, *, limit=10, country=None, admin1=None, state=None, near=None, radius_km=None, bbox=None,
         within=None, kinds=None, prefix=False, strict=True, worldview=None, geometry=False):  # fmt: skip
    """Places named `text`, best first, as Entities (placewise.model.Entity).

    text: a name ("Lake Tahoe"), a name with context ("Paris, TX", "Union Station, Toronto"), a
        code (YYZ, CYYZ, M5V, 94105, 560001, CA-ON, US, IND, Q1049470), a placewise id
        ("census:0646870") or coordinates ("43.6426, -79.3871", a map URL).
    country: alpha-2, alpha-3, numeric, name or alias ("US", "USA", "United States"), or a list.
    admin1 / state: "TX", "Texas", "US-TX", "Ontario", "KA" (one or a list).
    near: (lat, lon) to prefer places close to it; with radius_km, only places within it.
    bbox: (south, west, north, east); within: a place id or name ("GTA", "region:sf-bay-area").
    kinds: PlaceKind values or everyday words ("city", "park", "water", "airport", "postal_code").
    strict: False turns every filter above into a boost.
    prefix: match names that start with `text` (type-ahead).
    worldview: the worldview for the country of places in disputed areas (docs/worldviews.md).
    geometry: True adds each Entity's outline (slower for big places).
    Context in the text and these arguments combine; the arguments win on conflict."""
    return _default().find(
        text, limit=limit, country=country, admin1=admin1, state=state, near=near, radius_km=radius_km,
        bbox=bbox, within=within, kinds=kinds, prefix=prefix, strict=strict, worldview=worldview,
        geometry=geometry,
    )  # fmt: skip


def get(ident, *, worldview=None, geometry=False):
    """The Entity with placewise id `ident` ("census:0646870", "iso:IN-KA", "wikidata:Q1049470",
    "geo:43.6426,-79.3871"); KeyError when the open packs don't have it."""
    return _default().get(ident, worldview=worldview, geometry=geometry)


def outline(ident, simplify_m=None):
    """The outline of the place with id `ident` as a GeoJSON geometry dict ((lon, lat) order, a
    Polygon or MultiPolygon with each hole under its ring), simplified to within simplify_m metres
    if given; None for a place known only as a point; KeyError when the open packs don't have it.
    `placewise.get(ident, geometry=True).geojson()` gives the whole Feature."""
    return _default().outline(ident, simplify_m)


def suggest(text, limit=10, **context):
    """Type-ahead: `find(text, prefix=True)` with the same context arguments."""
    return _default().find(text, limit=limit, prefix=True, **context)
