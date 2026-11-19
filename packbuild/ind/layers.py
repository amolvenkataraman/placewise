"""The India pack's LGD-keyed polygon layers, each a union of PIN area pieces (packbuild.india):
`states`, `districts` and `cities` (urban local bodies), plus the PIN pieces themselves.

A piece is a PIN area, or the part of one on either side of India's de facto boundary
(packbuild.ind.defacto); every row carries `india_view_only`. A unit with pieces on both sides
has two rows: `lgd:district:9` (in India's de facto area) and `lgd:district:9#india-view` (the
rest), both named alike; the engine shows the second only under the IN worldview.

Unions dissolve the pieces' shared edges exactly (regions_layer.union), unsimplified, so a
union answers exactly as its pieces do.
"""

from collections import defaultdict
from dataclasses import dataclass

from placewise.constants import naming as naming_const
from placewise.packs import IdTemplate

from ..layer import LayerData
from ..regions_layer import region_area_km2, union

SUFFIX = naming_const.IND_VIEW_ONLY_SUFFIX
PIN_ID_TEMPLATE = IdTemplate("pin:{pincode}")  # the india-view pieces keep their own ids
# words LGD puts in ULB names that people leave out ("Srinagar Municipal Corporation" -> Srinagar)
ULB_TYPE_WORDS = (
    "Municipal Corporation", "City Municipal Corporation", "City Corporation", "Municipal Council",
    "City Municipal Council", "Town Municipal Council", "Municipal Committee", "Municipal Board",
    "Nagar Panchayat", "Nagar Palika Parishad", "Nagar Palika", "Town Panchayat", "Notified Area Council",
)  # fmt: skip


@dataclass(frozen=True)
class Piece:
    pin: int  # index of its PIN area
    rings: tuple  # (n, 2) (lon, lat) arrays, shells clockwise
    view_only: bool


def display_name(lgd_name):
    """A ULB's name without its type words, front or back ("Municipal Committee Uri" -> Uri)."""
    name = " ".join(lgd_name.split())
    for word in sorted(ULB_TYPE_WORDS, key=len, reverse=True):
        if name.lower().endswith(" " + word.lower()):
            return name[: -len(word) - 1].strip(" -,") or name
        if name.lower().startswith(word.lower() + " "):
            return name[len(word) + 1 :].strip(" -,") or name
    return name


def grouped(pieces, key_of):
    """{(key, view_only): [rings...]} for pieces whose PIN area has a key."""
    out = defaultdict(list)
    for p in pieces:
        key = key_of[p.pin]
        if key:
            out[key, p.view_only].extend(p.rings)
    return out


def union_rows(groups, fid):
    """[(key, view_only, Feature, km2)] for every group, ids fid(key) (+ SUFFIX for view-only
    pieces of a unit that also has pieces in India), smallest first within each key."""
    rows = []
    for (key, view_only), rings in sorted(groups.items()):
        both = (key, not view_only) in groups
        ident = fid(key) + (SUFFIX if view_only and both else "")
        feature = union(ident, rings)
        rows.append((key, view_only, ident, feature, region_area_km2(feature)))
    return rows


def polygon_layer(name, rows, columns, sources):
    """A LayerData from union_rows and {column: f(key) -> value} (all str unless noted)."""
    data = {"id": [r[2] for r in rows]}
    types = {"id": "str"}
    for col, (fn, kind) in columns.items():
        data[col] = [fn(r[0]) for r in rows]
        types[col] = kind
    data["india_view_only"] = [r[1] for r in rows]
    data["area_km2"] = [round(r[4], 2) for r in rows]
    types |= {"india_view_only": "bool", "area_km2": "f8"}
    return LayerData(name, "polygon", data, sources, features=[r[3] for r in rows], types=types)


def states_layer(pieces, state_of_pin, directory, names, sources):
    rows = union_rows(grouped(pieces, state_of_pin), lambda c: f"lgd:state:{c}")
    s = directory.states
    cols = {
        "name": (lambda c: names.name("state", c, s[c].name), "str"),
        "iso": (lambda c: s[c].iso, "str"),
        "lgd": (lambda c: c, "str"),
        "kind": (lambda c: s[c].kind, "str"),
        "aliases": (lambda c: "|".join(names.other_names("state", c)), "str"),
    }
    return polygon_layer("states", rows, cols, sources)


def districts_layer(pieces, district_of_pin, directory, names, sources):
    rows = union_rows(grouped(pieces, district_of_pin), lambda c: f"lgd:district:{c}")
    d = directory.districts
    cols = {
        "name": (lambda c: names.name("district", c, d[c].name), "str"),
        "lgd": (lambda c: c, "str"),
        "lgd_name": (lambda c: d[c].name, "str"),
        "state_code": (lambda c: d[c].iso, "str"),
        "census2011": (lambda c: d[c].census2011 if d[c].census2011 not in ("", "0") else "", "str"),
        "aliases": (lambda c: "|".join(names.other_names("district", c)), "str"),
    }
    return polygon_layer("districts", rows, cols, sources)


def cities_layer(pieces, city_of_pin, city_info, sources):
    """`city_info[code]`: dict name, official_name, type, state_code, district, census2011,
    local_name, aliases (list), members (LGD codes it stands for)."""
    rows = union_rows(grouped(pieces, city_of_pin), lambda c: f"lgd:ulb:{c}")
    rows.sort(key=lambda r: (r[4], r[2]))  # smallest first: a city inside another's box wins ties
    info = city_info
    cols = {
        "name": (lambda c: info[c]["name"], "str"),
        "official_name": (lambda c: info[c]["official_name"], "str"),
        "lgd": (lambda c: c, "str"),
        "members": (lambda c: ",".join(info[c]["members"]), "str"),
        "type": (lambda c: info[c]["type"], "str"),
        "state_code": (lambda c: info[c]["state_code"], "str"),
        "district": (lambda c: info[c]["district"], "str"),
        "census2011": (lambda c: info[c]["census2011"], "str"),
        "local_name": (lambda c: info[c]["local_name"], "str"),
        "aliases": (lambda c: "|".join(info[c]["aliases"]), "str"),
    }
    return polygon_layer("cities", rows, cols, sources)


def city_info(codes, directory, names, district_of_city):
    """{city code: city_info dict} (cities_layer) for the cities in `codes`: LGD's ULB, with the
    curated name and other names (names/ind.json units), or a curated city (names.cities) for
    one LGD lists no longer (BBMP) or several it stands for (Delhi)."""
    curated = {c["id"].rpartition(":")[2]: c for c in names.cities}
    out = {}
    for code in sorted(set(codes) - {""}):
        unit, cur = directory.ulbs.get(code), curated.get(code)
        district = district_of_city.get(code, "")
        if cur is not None:
            other = [f["name"] for f in cur.get("former", ())] + list(cur.get("aliases", ()))
            first = directory.ulbs.get(cur["lgd"][0])
            out[code] = {
                "name": cur["name"], "official_name": cur.get("official_name", cur["name"]),
                "type": first.kind if first else "Municipal Corporation", "state_code": f"IN-{cur['state']}",
                "district": district, "census2011": first.census2011 if first else "",
                "local_name": first.local_name if first and len(cur["lgd"]) == 1 else "",
                "aliases": list(dict.fromkeys(other)), "members": list(cur["lgd"]),
            }  # fmt: skip
            continue
        name = names.name("ulb", code, display_name(unit.name))
        other = [n for n in names.other_names("ulb", code) if n != name]
        if unit.name != name and unit.name not in other:
            other.append(unit.name)
        out[code] = {
            "name": name, "official_name": unit.name, "type": unit.kind, "state_code": unit.iso,
            "district": district, "census2011": unit.census2011, "local_name": unit.local_name,
            "aliases": other, "members": [code],
        }  # fmt: skip
    return out


def pincodes_layer(pincodes, pieces, extra, sources):
    """The pincodes layer as pieces: a PIN area wholly in India keeps its feature and id; one
    reaching a neighbour's ground becomes its India part (`pin:<code>`) and the rest
    (`pin:<code>#india-view`, or `pin:<code>` when nothing is in India). Every row carries the
    PIN area's columns, `extra` ({column: per-PIN values, all str}) and `india_view_only`."""
    split = defaultdict(int)
    for p in pieces:
        split[p.pin] += 1
    cols = pincodes.columns
    data = {k: [] for k in (*cols, *extra, "india_view_only")}
    features = []
    for p in pieces:
        base = cols["id"][p.pin]
        ident = base + (SUFFIX if p.view_only and split[p.pin] > 1 else "")
        for k, values in (*cols.items(), *extra.items()):
            data[k].append(ident if k == "id" else values[p.pin])
        data["india_view_only"].append(p.view_only)
        whole = split[p.pin] == 1 and not p.view_only
        features.append(pincodes.features[p.pin] if whole else union(ident, p.rings))
    types = dict(pincodes.types) | {k: "str" for k in extra} | {"india_view_only": "bool"}
    return LayerData(
        "pincodes", "polygon", data, sources, features=features, types=types, id_template=PIN_ID_TEMPLATE
    )
