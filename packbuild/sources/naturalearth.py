"""Natural Earth 1:10m (public domain): the `countries`, `admin1` and `worldviews` polygon layers.

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

from placewise.constants import worldviews as worldview_const
from placewise.io import read_shapefile
from placewise.model import Feature

from ..layer import LayerData

SOURCE = "naturalearth"

_WORLDVIEW = re.compile(r"^(ADM0_A3|FCLASS)_([A-Z]{2,3})$", re.IGNORECASE)
_VIEW_UNIT = re.compile(r"^ADM0_A3_([A-Z]{2,3})$", re.IGNORECASE)
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


def label_points(shp_path):
    """{alpha-2: (lat, lon)}: each country's map label point (LABEL_Y, LABEL_X). A code several
    units share goes to the unit that is the country itself, as in `countries`; files without
    label attributes give {}."""
    found, shared = {}, Counter()
    rows = []
    for feature in read_shapefile(shp_path):
        p = feature.properties
        code = _code(p.get("ISO_A2_EH"), _ISO2)
        if code and p.get("LABEL_X") is not None and p.get("LABEL_Y") is not None:
            shared[code] += 1
            rows.append((code, _text(p.get("ADM0_A3")) == _text(p.get("ISO_A3_EH")), p))
    for code, is_country, p in rows:
        if shared[code] == 1 or is_country:
            found[code] = (float(p["LABEL_Y"]), float(p["LABEL_X"]))
    return found


def admin1(shp_path, english=None):
    """Admin-1 units (states, provinces, ...). id is "iso:<iso_3166_2>"; placeholder codes such as
    "-99-X11~" or "AI-X00", and codes Natural Earth gives to more than one feature (Bosnia's
    cantons all read "BA-BIH"), fall back to "ne:<adm1_code>". `geonames` is Natural Earth's
    GeoNames id for the unit ("geonames:6093943"), for joining GeoNames alternate names.

    `name` is English (english_names): `english` ({id: name}, the curated datasets/names/admin1.json)
    first, else Natural Earth's name_en, else its name; `name_local` is Natural Earth's name where
    it differs (Noord-Holland, Nordrhein-Westfalen), kept for search. `region` and `region_code`
    are Natural Earth's grouping of the units, where it gives one: for France and Italy the ISO
    3166-2 first-level region its departments and provinces belong to (Île-de-France, FR-IDF)."""
    raw = read_shapefile(shp_path)
    props = [f.properties for f in raw]
    iso = [_text(p.get("iso_3166_2")) for p in props]
    valid = [bool(_ISO_3166_2.match(c)) for c in iso]
    counts = Counter(c for c, ok in zip(iso, valid, strict=True) if ok)
    ids = [
        f"iso:{c}" if ok and counts[c] == 1 else f"ne:{_text(p.get('adm1_code'))}"
        for c, ok, p in zip(iso, valid, props, strict=True)
    ]
    local = [_text(p.get("name")) for p in props]
    names = english_names(ids, props, english or {})
    columns = {
        "id": ids,
        "name": names,
        "name_local": [n if n != e else "" for n, e in zip(local, names, strict=True)],
        "region": [_text(p.get("region")) for p in props],
        "region_code": [_text(p.get("region_cod")) for p in props],
        "country": [_code(p.get("iso_a2"), _ISO2) for p in props],
        "code": [c.split("-", 1)[1] if ok else "" for c, ok in zip(iso, valid, strict=True)],
        "adm0_a3": [_text(p.get("adm0_a3")) for p in props],
        "type_en": [_text(p.get("type_en")) for p in props],
        "name_alt": [_text(p.get("name_alt")) for p in props],
        "geonames": [_geonames_id(p.get("gn_id")) for p in props],
    }
    columns.update(_worldview_columns(props))
    types = {name: "str" for name in columns}
    return LayerData("admin1", "polygon", columns, (SOURCE,), features=_with_ids(raw, ids), types=types)


def english_names(ids, props, english):
    """Each unit's English name: the curated one, else Natural Earth's name_en (it fixes NE's own
    typos: "Seien-et-Marne"), except where name_en is the country's name (Hovedstaden: "Denmark")
    or another unit of that country has the same name_en (Latvia's municipalities named after
    their old district), where Natural Earth's name stays; else its name."""
    en = [_text(p.get("name_en")) for p in props]
    country = [_text(p.get("iso_a2")) for p in props]
    shared = Counter((c, e) for c, e in zip(country, en, strict=True) if e)
    out = []
    for pid, p, c, e in zip(ids, props, country, en, strict=True):
        own = _text(p.get("name"))
        if pid in english:
            out.append(english[pid])
        elif e and shared[c, e] == 1 and e != _text(p.get("admin")):
            out.append(e)
        else:
            out.append(own)
    return out


def disputed_areas(shp_path):
    """Natural Earth's disputed areas (Aksai Chin, Crimea, Kosovo ...: 99 polygons in 5.1.2) as the
    `worldviews` layer. They overlay the countries polygons (none overlaps another) and say, per
    view, which admin-0 unit each area belongs to; together with the countries' own view columns
    they reproduce Natural Earth's point-of-view countries files. id is "ne:<NE_ID>"; name is the
    area's (BRK_NAME, Natural Earth's typos corrected); adm0_a3 is the unit that holds it."""
    raw = read_shapefile(shp_path)
    props = [f.properties for f in raw]
    ids = [f"ne:{int(p.get('NE_ID') or 0)}" for p in props]
    names = [_text(p.get("BRK_NAME")).lstrip("\ufeff") or _text(p.get("NAME")) for p in props]
    columns = {
        "id": ids,
        "name": [worldview_const.AREA_NAMES.get(n, n) for n in names],
        "adm0_a3": [_text(p.get("ADM0_A3")) for p in props],
        "type": [_text(p.get("TYPE")) for p in props],
        "note": [_text(p.get("NOTE_BRK")) for p in props],
    }
    views = sorted({k for p in props for k in p if _VIEW_UNIT.match(k)})
    columns.update({name.lower(): [_text(p.get(name)) for p in props] for name in views})
    types = {name: "str" for name in columns}
    layer = worldview_const.WORLDVIEWS
    return LayerData(layer, "polygon", columns, (SOURCE,), features=_with_ids(raw, ids), types=types)


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


def _geonames_id(value):
    """ "geonames:<id>" for Natural Earth's gn_id, or "" where it has none (-1, 0, missing)."""
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return ""
    return f"geonames:{number}" if number > 0 else ""


def _code(value, pattern):
    """An ISO code, or "" for Natural Earth's "-99" / "-1" placeholders."""
    value = _text(value)
    return value if pattern.match(value) else ""
