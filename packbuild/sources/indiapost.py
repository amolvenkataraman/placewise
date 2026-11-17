"""Department of Posts, India (GODL-India): the `pincodes` polygon layer and `post_offices` point layer.

Two datasets from the Open Government Data Platform India (data.gov.in):

- All India Pincode Boundary: GeoJSON (CRS84), one feature per delivery PIN code area with
  Pincode, Office_Name, Division, Region and Circle (text padded with trailing spaces). It names no
  district or state.
- All India Pincode Directory: CSV, one row per post office: CircleName, RegionName, DivisionName,
  OfficeName, Pincode, OfficeType (HO head, PO sub, BO branch office), Delivery ("Delivery" /
  "Non Delivery"), District, StateName, Latitude, Longitude. The data.gov.in API export spells the
  same headers in lower case; both are accepted.

A PIN code's district and state are joined from the directory: the (district, state) most of its
offices are filed under, ties going to the higher office (HO, then PO, then BO), then alphabetically.
A PIN area may cross district lines, so this is the postal answer, not an administrative one.

Directory coordinates are used only when both parse as plain numbers inside India's extent; "NA",
the 1/1 placeholder and values with stray characters (a trailing "-", a hemisphere letter) are
dropped, never repaired.
"""

import csv
import logging
import re
from collections import Counter, defaultdict

from placewise.model import Feature

from ..layer import LayerData
from ._india import ISO_NAMES, normalise_name, read_wgs84_geojson, text

BOUNDARY_SOURCE = "indiapost-pincode-boundary"
DIRECTORY_SOURCE = "indiapost-pincode-directory"

_PIN = re.compile(r"^[1-9]\d{5}$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
# generous box round India and its islands (degrees); points outside it are placeholders or typos
INDIA_EXTENT = (6.0, 68.0, 38.0, 98.0)  # south, west, north, east
_OFFICE_RANK = {"HO": 0, "PO": 1, "SO": 1, "BO": 2}
_DIRECTORY_FIELDS = {
    "circle": "circlename", "region": "regionname", "division": "divisionname", "office": "officename",
    "pincode": "pincode", "office_type": "officetype", "delivery": "delivery", "district": "district",
    "state": "statename", "latitude": "latitude", "longitude": "longitude",
}  # fmt: skip

# state names (normalised) -> ISO 3166-2 code; the directory's 36 names all match ISO's English ones
STATE_CODES = {normalise_name(name): code for code, name in ISO_NAMES.items()}

log = logging.getLogger(__name__)


def state_code(name):
    """ISO 3166-2 code ("IN-KA") for a state or union territory name, "" if unknown."""
    return STATE_CODES.get(normalise_name(name or ""), "")


def read_directory(path):
    """Directory rows as dicts with the keys of _DIRECTORY_FIELDS, values trimmed."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = [h.strip().lower() for h in next(reader, [])]
        missing = [k for k in _DIRECTORY_FIELDS.values() if k not in header]
        if missing:
            names = ", ".join(_header_name(k) for k in missing)
            raise ValueError(f"{path}: not the All India Pincode Directory CSV; it lacks {names}")
        index = {key: header.index(column) for key, column in _DIRECTORY_FIELDS.items()}
        for row in reader:
            if row:
                yield {key: text(row[i]) if i < len(row) else "" for key, i in index.items()}


def pincode_districts(rows):
    """{pincode: (district, state)} by majority of offices; ties to the higher office, then by name."""
    votes = defaultdict(Counter)
    best_rank = defaultdict(dict)
    for r in rows:
        key = (r["district"], r["state"])
        votes[r["pincode"]][key] += 1
        rank = _OFFICE_RANK.get(r["office_type"], 3)
        best_rank[r["pincode"]][key] = min(rank, best_rank[r["pincode"]].get(key, rank))
    return {
        pin: min(counts, key=lambda k, pin=pin, counts=counts: (-counts[k], best_rank[pin][k], k))
        for pin, counts in votes.items()
    }


def pincodes(boundary_path, directory_path=None):
    """The pincodes layer: one feature per PIN code (several source polygons of one PIN code become
    one multi-part feature, at the first one's position); features without a valid PIN are dropped."""
    raw = read_wgs84_geojson(boundary_path)
    order, outlines, props = [], {}, {}
    dropped = 0
    for feature in raw:
        pin = text(feature.properties.get("Pincode"))
        if not _PIN.match(pin):
            dropped += 1
            continue
        if pin not in outlines:
            order.append(pin)
            outlines[pin], props[pin] = [], feature.properties
        outlines[pin].extend(feature.outlines)
    if dropped:
        log.info("pincodes: dropped %d features without a valid PIN code", dropped)
    districts = pincode_districts(read_directory(directory_path)) if directory_path is not None else {}
    district = [districts.get(pin, ("", "")) for pin in order]
    columns = {
        "id": [f"pin:{pin}" for pin in order],
        "name": [text(props[pin].get("Office_Name")) or pin for pin in order],
        "pincode": order,
        "division": [text(props[pin].get("Division")) for pin in order],
        "region": [text(props[pin].get("Region")) for pin in order],
        "circle": [text(props[pin].get("Circle")) for pin in order],
        "district": [d for d, _ in district],
        "state": [s for _, s in district],
        "state_code": [state_code(s) for _, s in district],
    }
    features = [Feature(tuple(outlines[pin]), {}, f"pin:{pin}") for pin in order]
    sources = (BOUNDARY_SOURCE,) if directory_path is None else (BOUNDARY_SOURCE, DIRECTORY_SOURCE)
    types = {name: "str" for name in columns}
    return LayerData("pincodes", "polygon", columns, sources, features=features, types=types)


def post_offices(directory_path):
    """The post_offices layer: every office with usable coordinates. id is
    "indiapost:<pincode>:<office name>"; exact duplicate rows are kept once, and a name repeated
    under one PIN code with different details gets "#2", "#3", ... in source order."""
    seen, ids = set(), Counter()
    rows, lat, lon, unusable = [], [], [], 0
    for r in read_directory(directory_path):
        record = tuple(r.values())
        if record in seen:
            continue
        seen.add(record)
        point = _coordinates(r["latitude"], r["longitude"])
        if point is None:
            unusable += 1
            continue
        key = f"indiapost:{r['pincode']}:{r['office']}"
        ids[key] += 1
        r["id"] = key if ids[key] == 1 else f"{key}#{ids[key]}"
        rows.append(r)
        lat.append(point[0])
        lon.append(point[1])
    if unusable:
        log.info("post_offices: %d offices without usable coordinates left out", unusable)
    columns = {
        "id": [r["id"] for r in rows],
        "name": [r["office"] for r in rows],
        "pincode": [r["pincode"] for r in rows],
        "office_type": [r["office_type"] for r in rows],
        "delivery": [r["delivery"].lower() == "delivery" for r in rows],
        "division": [r["division"] for r in rows],
        "region": [r["region"] for r in rows],
        "circle": [r["circle"] for r in rows],
        "district": [r["district"] for r in rows],
        "state": [r["state"] for r in rows],
        "state_code": [state_code(r["state"]) for r in rows],
    }
    types = {name: "str" for name in columns}
    types["delivery"] = "bool"
    return LayerData("post_offices", "point", columns, (DIRECTORY_SOURCE,), lat=lat, lon=lon, types=types)


def _coordinates(lat, lon):
    if not (_NUMBER.match(lat) and _NUMBER.match(lon)):
        return None
    lat, lon = float(lat), float(lon)
    south, west, north, east = INDIA_EXTENT
    return (lat, lon) if south <= lat <= north and west <= lon <= east else None


def _header_name(key):
    """The data.gov.in CSV spelling of a lower-cased header, for error messages."""
    names = {
        "circlename": "CircleName", "regionname": "RegionName", "divisionname": "DivisionName",
        "officename": "OfficeName", "pincode": "Pincode", "officetype": "OfficeType", "delivery": "Delivery",
        "district": "District", "statename": "StateName", "latitude": "Latitude", "longitude": "Longitude",
    }  # fmt: skip
    return names[key]
