"""The India pack's `neighbourhoods` point layer: post-office names inside cities (India Post,
GODL-India; the city from the LGD crosswalk).

In cities, a post office is named after its neighbourhood ("Koramangala S.O",
"Whitefield S.O", "Indiranagar S.O (Bengaluru)"). From the offices the build keeps (inside or
near their own PIN area, indiapost.keep_placed_offices) whose PIN area belongs to a city, the
name before the type word (engine.naming.rules.office_area_name) is a neighbourhood, unless it
names an institution (the curated not_neighbourhoods words: "Medical College", "High Court" ...)
or the city itself. One point per (city, name): the head office's, else a sub office's, else a
branch office's; delivery offices before non-delivery ones; then the directory's order.
"""

import re

import numpy as np

from placewise.engine.naming.rules import fold, office_area_name
from placewise.packs import IdTemplate

from ..layer import LayerData
from ..sources.indiapost import DIRECTORY_SOURCE

LGD_SOURCE = "lgd-directory"  # the city each point belongs to
ID_TEMPLATE = IdTemplate("indiapost:{pincode}:{office}")  # the office's own id
_RANK = {"HO": 0, "PO": 1, "SO": 1, "BO": 2}


def neighbourhood_name(office, exclude):
    """The neighbourhood an office's name gives, or "" for an institution (any `exclude` word, as
    whole words, case ignored) or a bare number."""
    name = office_area_name(office)
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()  # "(Bengaluru)" qualifiers
    if not name or name.isdigit():
        return ""
    low = f" {re.sub(r'[^a-z0-9]+', ' ', name.lower())} "
    for word in exclude:
        w = re.sub(r"[^a-z0-9]+", " ", word.lower()).strip()
        if w and f" {w} " in low:
            return ""
    return name


def neighbourhoods(offices, city_of_pin, city_names, exclude=()):
    """The layer from a post_offices LayerData; `city_of_pin` {pincode: city id}, `city_names`
    {city id: its names (name, aliases ...)}: an office named like its city is no neighbourhood."""
    own = {city: {fold(n) for n in names} for city, names in city_names.items()}
    c = offices.columns
    best = {}
    for k in range(len(c["id"])):
        city = city_of_pin.get(c["pincode"][k])
        if not city:
            continue
        name = neighbourhood_name(c["name"][k], exclude)
        if not name or fold(name) in own.get(city, ()):
            continue
        rank = (_RANK.get(c["office_type"][k], 3), not c["delivery"][k], k)
        key = (city, fold(name))
        if key not in best or rank < best[key][0]:
            best[key] = (rank, k, name)
    chosen = sorted(best.values(), key=lambda v: v[1])
    rows = [k for _, k, _ in chosen]
    columns = {
        "id": [c["id"][k] for k in rows],
        "name": [n for _, _, n in chosen],
        "city": [city_of_pin[c["pincode"][k]] for k in rows],
        "pincode": [c["pincode"][k] for k in rows],
        "office": [c["name"][k] for k in rows],
        "office_type": [c["office_type"][k] for k in rows],
    }
    lat = np.asarray(offices.lat, dtype=np.float64)[rows]
    lon = np.asarray(offices.lon, dtype=np.float64)[rows]
    types = {name: "str" for name in columns}
    sources = (DIRECTORY_SOURCE, LGD_SOURCE)
    return LayerData(
        "neighbourhoods", "point", columns, sources, lat=lat, lon=lon, types=types, id_template=ID_TEMPLATE
    )
