"""Wikidata (CC0) parks as points: national parks, tiger reserves, wildlife refuges and India's
protected areas, outside the countries whose park packs have outlines (US, Canada).

Each SPARQL result (the registry's `parks_*` downloads) has rows of `item`, `name` (English label),
`coord` (P625), `area` (P2046, normalised to m²), `cc` (P17's ISO alpha-2, only to leave out the
outline countries; parks carry no country of their own) and `sitelinks`; an item repeats once
per value of each. A park's radius is that of a circle of its area (the largest area given),
capped at POINT_RADIUS_CAP_KM, or 0 without an area: the engine treats it as "in the area of"
within the circle and "near" up to its tier's distance beyond, never "within".

Tier: the query's class (national park and tiger reserve 1, wildlife refuge 2), raised by the
name's own words (tiers.name_tier: India's items are often typed just "protected area"), else 3.
"""

import json
import logging
import math
import re
from pathlib import Path

import numpy as np

from placewise.constants.parks import NATIONAL, POINT_RADIUS_CAP_KM, REGIONAL, STATE

from ...fetch import fetch as fetch_file
from ...layer import LayerData
from .. import url
from . import tiers

SOURCE = "wikidata"
# download name -> (tier, designation) of the items it lists
QUERIES = {
    "parks_national": (NATIONAL, "National Park"),
    "parks_tiger_reserves": (NATIONAL, "Tiger Reserve"),
    "parks_wildlife_refuges": (STATE, "Wildlife Refuge"),
    "parks_india": (REGIONAL, "Protected Area"),
}
OUTLINE_COUNTRIES = frozenset({"US", "CA"})  # usa-parks and can-parks have these parks' outlines
_POINT = re.compile(r"^Point\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)$")
_DESIGNATION_WORDS = (
    ("tiger reserve", "Tiger Reserve"),
    ("national park", "National Park"),
    ("wildlife sanctuary", "Wildlife Sanctuary"),
    ("bird sanctuary", "Bird Sanctuary"),
)
log = logging.getLogger(__name__)


def fetch(cache_dir, refresh=False):
    """{download name: cached result}; each query gets its own folder (every URL ends in /sparql)."""
    return {
        name: fetch_file(
            url(SOURCE, name), Path(cache_dir) / f"wikidata-{name.replace('_', '-')}", refresh=refresh
        )
        for name in QUERIES
    }


def read(paths):
    """{qid: park dict} from the query results {download name: path}, the most significant tier
    winning when an item is in several."""
    parks = {}
    for name, path in paths.items():
        tier, designation = QUERIES[name]
        for row in json.loads(Path(path).read_text(encoding="utf-8"))["results"]["bindings"]:
            qid = row["item"]["value"].rsplit("/", 1)[-1]
            point = _POINT.match(row["coord"]["value"])  # other globes' coordinates start with "<"
            label = " ".join(row["name"]["value"].split())
            if not point or not label or label == qid:
                continue
            found = parks.setdefault(qid, {
                "name": label, "lat": float(point[2]), "lon": float(point[1]), "tier": tier,
                "designation": designation, "area": 0.0, "countries": set(),
                "sitelinks": int(row["sitelinks"]["value"]),
            })  # fmt: skip
            if tier < found["tier"]:
                found["tier"], found["designation"] = tier, designation
            if "area" in row:
                found["area"] = max(found["area"], float(row["area"]["value"]) / 1e6)
            if "cc" in row:
                found["countries"].add(row["cc"]["value"].upper())
    for found in parks.values():
        by_name = tiers.name_tier(found["name"])
        if by_name is not None and by_name < found["tier"]:
            found["tier"] = by_name
        lower = found["name"].lower()
        found["designation"] = next((d for w, d in _DESIGNATION_WORDS if w in lower), found["designation"])
    return parks


def park_points(paths):
    """The `park_points` layer: every park outside OUTLINE_COUNTRIES, by Wikidata id."""
    parks = read(paths)
    shared = {q: p for q, p in parks.items() if len(p["countries"]) > 1}
    if shared:  # parks Wikidata places in more than one country: the boundary layers decide
        log.info("wikidata parks in several countries: %s",
                 ", ".join(f"{p['name']} ({'/'.join(sorted(p['countries']))})" for p in shared.values()))  # fmt: skip  # noqa: E501
    kept = sorted(
        (q for q, p in parks.items() if not p["countries"] & OUTLINE_COUNTRIES), key=lambda q: int(q[1:])
    )
    rows = [parks[q] for q in kept]
    area = np.array([p["area"] or np.nan for p in rows], dtype=np.float32)
    columns = {
        "id": [f"wikidata:{q}" for q in kept],
        "name": [p["name"] for p in rows],
        "tier": np.array([p["tier"] for p in rows], dtype=np.uint8),
        "designation": [p["designation"] for p in rows],
        "area_km2": area,
        "radius_km": np.array([radius_km(p["area"]) for p in rows], dtype=np.float32),
        "wikidata": kept,
        "sitelinks": np.array([p["sitelinks"] for p in rows], dtype=np.int32),
        "aliases": [tiers.short_name(p["name"], p["designation"]) for p in rows],
    }
    lat = np.array([p["lat"] for p in rows])
    lon = np.array([p["lon"] for p in rows])
    return LayerData("park_points", "point", columns, (SOURCE,), lat=lat, lon=lon)


def radius_km(area_km2):
    """The radius of a circle of the area, capped; 0 for no area."""
    if not area_km2 or area_km2 <= 0:
        return 0.0
    return min(math.sqrt(area_km2 / math.pi), POINT_RADIUS_CAP_KM)
