"""Natural Earth 1:10m (public domain): the `countries` and `admin1` polygon layers.

Natural Earth's default files draw borders "de facto" (who administers the ground). It also ships
per-country point-of-view attributes: `ADM0_A3_XX` (how worldview XX groups each unit into a
country) and `FCLASS_XX` (how XX classes it: country, dependency, unrecognized, ...). These are
kept verbatim, lower-cased, as str columns so placewise can offer a worldview choice later.

Feature order: Natural Earth's countries and admin-1 polygons tile the land without overlapping
(checked on 5.1.1: none of ~59,000 random land points falls in two features of either layer), so
"most specific first" ordering isn't needed and features keep the source's order.
"""

import re
from collections import Counter

from placewise.io import read_shapefile
from placewise.model import Feature

from ..layer import LayerData

SOURCE = "naturalearth"

_WORLDVIEW = re.compile(r"^(ADM0_A3|FCLASS)_([A-Z]{2,3})$", re.IGNORECASE)
_ISO2 = re.compile(r"^[A-Z]{2}$")
_ISO3 = re.compile(r"^[A-Z]{3}$")
_ISO_3166_2 = re.compile(r"^([A-Z]{2})-(?!X\d+$)([A-Z0-9]{1,3})$")  # NE invents "XX-X01" (often with "~")


def countries(shp_path):
    """Admin-0 units. id is "iso:<ISO_A2_EH>"; units without an ISO code ("-99"), and dependencies
    that share their country's code (Coral Sea Is. and Australia are both "AU"), use
    "ne:<ADM0_A3>", Natural Earth's own code, so ids stay unique and "iso:" is never invented."""
    raw = read_shapefile(shp_path)
    props = [f.properties for f in raw]
    iso2 = [_code(p.get("ISO_A2_EH"), _ISO2) for p in props]
    iso3 = [_code(p.get("ISO_A3_EH"), _ISO3) for p in props]
    adm0 = [_text(p.get("ADM0_A3")) for p in props]
    shared = {code for code, n in Counter(iso2).items() if code and n > 1}
    ids = []
    for code, a3, i3 in zip(iso2, adm0, iso3, strict=True):
        owner = code and (code not in shared or a3 == i3)  # a shared code goes to the country itself
        ids.append(f"iso:{code}" if owner else f"ne:{a3}")
    columns = {
        "id": ids,
        "name": [_text(p.get("NAME_EN")) or _text(p.get("NAME")) for p in props],
        "iso2": iso2,
        "iso3": iso3,
        "adm0_a3": adm0,
        "sovereign": [_text(p.get("SOVEREIGNT")) for p in props],
        "type": [_text(p.get("TYPE")) for p in props],
        "continent": [_text(p.get("CONTINENT")) for p in props],
        "population": [int(p.get("POP_EST") or 0) for p in props],
    }
    columns.update(_worldview_columns(props))
    types = {name: "str" for name in columns}
    types["population"] = "i8"
    return LayerData("countries", "polygon", columns, (SOURCE,), features=_with_ids(raw, ids), types=types)


def admin1(shp_path):
    """Admin-1 units (states, provinces, ...). id is "iso:<iso_3166_2>"; placeholder codes such as
    "-99-X11~" or "AI-X00", and codes Natural Earth gives to more than one feature (Bosnia's cantons all read
    "BA-BIH"), fall back to "ne:<adm1_code>"."""
    raw = read_shapefile(shp_path)
    props = [f.properties for f in raw]
    iso = [_text(p.get("iso_3166_2")) for p in props]
    valid = [bool(_ISO_3166_2.match(c)) for c in iso]
    counts = Counter(c for c, ok in zip(iso, valid, strict=True) if ok)
    ids = [
        f"iso:{c}" if ok and counts[c] == 1 else f"ne:{_text(p.get('adm1_code'))}"
        for c, ok, p in zip(iso, valid, props, strict=True)
    ]
    columns = {
        "id": ids,
        "name": [_text(p.get("name")) for p in props],
        "country": [_code(p.get("iso_a2"), _ISO2) for p in props],
        "code": [c.split("-", 1)[1] if ok else "" for c, ok in zip(iso, valid, strict=True)],
        "adm0_a3": [_text(p.get("adm0_a3")) for p in props],
        "type_en": [_text(p.get("type_en")) for p in props],
        "name_alt": [_text(p.get("name_alt")) for p in props],
    }
    columns.update(_worldview_columns(props))
    types = {name: "str" for name in columns}
    return LayerData("admin1", "polygon", columns, (SOURCE,), features=_with_ids(raw, ids), types=types)


def worldviews(layer):
    """The worldview codes (e.g. "IN", "ISO", "US") a layer carries ADM0_A3_ or FCLASS_ columns for."""
    return sorted({m.group(2).upper() for name in layer.columns if (m := _WORLDVIEW.match(name))})


def _worldview_columns(props):
    names = sorted({k for p in props for k in p if _WORLDVIEW.match(k)})
    return {name.lower(): [_text(p.get(name)) for p in props] for name in names}


def _with_ids(raw, ids):
    return [Feature(f.outlines, {}, fid) for f, fid in zip(raw, ids, strict=True)]


def _text(value):
    """Clean text. Natural Earth pads .dbf text with NUL bytes, which read_shapefile keeps."""
    return "" if value is None else str(value).strip(" \t\r\n\x00")


def _code(value, pattern):
    """An ISO code, or "" for Natural Earth's "-99" / "-1" placeholders."""
    value = _text(value)
    return value if pattern.match(value) else ""
