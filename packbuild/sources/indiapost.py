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
dropped, never repaired. The build then keeps an office only if its point lies inside its own PIN
area or within OFFICE_BUFFER_KM of it (`keep_placed_offices`): about a third of the directory's
points are elsewhere, some in other states or outside India.
"""

import csv
import dataclasses
import logging
import re
import tempfile
from collections import Counter, defaultdict

import numpy as np

from placewise.constants.packs import E7
from placewise.model import Feature
from placewise.packs import open_pack

from ..layer import LayerData, write_pack
from ._india import ISO_NAMES, normalise_name, read_wgs84_geojson, text

BOUNDARY_SOURCE = "indiapost-pincode-boundary"
DIRECTORY_SOURCE = "indiapost-pincode-directory"

_PIN = re.compile(r"^[1-9]\d{5}$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
# generous box round India and its islands (degrees); points outside it are placeholders or typos
INDIA_EXTENT = (6.0, 68.0, 38.0, 98.0)  # south, west, north, east
# an office keeps its coordinates only inside its own PIN area or this close to it (km): PIN areas
# are generalised delivery zones and offices often sit on a boundary road, while an office farther
# out is in another area, so a lookup would name the wrong one (packbuild/README.md, India pack)
OFFICE_BUFFER_KM = 2.0
# office_placement measures an office's distance to its own PIN area only when it lies within this
# many degrees (plus the buffer) of the area's bbox
_BBOX_MARGIN_DEG = 0.5
_KM_PER_DEG_LAT = 110.5  # the least km per degree of latitude (at the equator), so margins err wide
PLACEMENTS = ("inside", "near", "elsewhere", "outside", "no_area")
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


def office_placement(offices, pincodes, buffer_km=OFFICE_BUFFER_KM):
    """Where each office (a post_offices layer) lies against its own PIN area (a pincodes layer),
    as an array of PLACEMENTS: "inside" it, "near" (outside it, but within buffer_km of its
    boundary), "elsewhere" (in another PIN area), "outside" (in no PIN area: off the coast, or
    outside India) or "no_area" (its PIN code has no polygon). The pincodes are written to a
    temporary pack so placewise's own pack geometry answers (distances exact on the sphere)."""
    count = len(offices.columns["id"])
    where = np.full(count, "outside", dtype=object)
    feature = {pin: i for i, pin in enumerate(pincodes.columns["pincode"])}
    own = np.array([feature.get(pin, -1) for pin in offices.columns["pincode"]], dtype=np.int64)
    where[own < 0] = "no_area"
    if not count:
        return where
    lat, lon = np.asarray(offices.lat, dtype=np.float64), np.asarray(offices.lon, dtype=np.float64)
    shapes = LayerData(
        "pincodes",
        "polygon",
        {"id": pincodes.columns["id"], "name": pincodes.columns["pincode"]},
        pincodes.sources,
        features=pincodes.features,
    )
    with tempfile.TemporaryDirectory(prefix="placewise-pin-check-") as tmp:
        pack_dir = write_pack(tmp, "pin-check", "2000.01", [shapes])
        areas = open_pack(pack_dir)["pincodes"]
        inside = areas.contains(lat, lon, own)
        where[inside] = "inside"
        rest = np.flatnonzero((own >= 0) & ~inside)
        if len(rest) and buffer_km > 0:
            bbox = np.load(pack_dir / "pincodes" / "geom" / "bbox.npy") / E7
            near = _near_own_area(areas, bbox, lat[rest], lon[rest], own[rest], buffer_km)
            where[rest[near]] = "near"
        rest = rest[where[rest] == "outside"]
        if len(rest):
            where[rest[np.asarray(areas.query(lat[rest], lon[rest])) >= 0]] = "elsewhere"
    return where


def _near_own_area(areas, bbox, lat, lon, own, buffer_km):
    """Whether each point is within buffer_km of its own feature's boundary (`areas`, a
    PolygonLayer, and its (n, 4) bbox in degrees): PolygonLayer.nearest_edge_km against that one
    feature only, for the points near its bbox. The margin is generous: PIN areas' great-circle
    edges stray from their vertices' bbox by far less than _BBOX_MARGIN_DEG."""
    margin = _BBOX_MARGIN_DEG + buffer_km / _KM_PER_DEG_LAT
    south, west, north, east = bbox[own].T
    lon_margin = margin / np.cos(
        np.radians(np.minimum(np.maximum(np.abs(south), np.abs(north)) + margin, 89))
    )
    close = np.flatnonzero(
        (lat >= south - margin)
        & (lat <= north + margin)
        & (lon >= west - lon_margin)
        & (lon <= east + lon_margin)
    )
    near = np.zeros(len(lat), dtype=bool)
    order = close[np.argsort(own[close], kind="stable")]
    cuts = np.flatnonzero(np.diff(own[order])) + 1
    for group in np.split(order, cuts) if len(order) else ():
        near[group] = areas.nearest_edge_km(lat[group], lon[group], int(own[group[0]])) <= buffer_km
    return near


def keep_placed_offices(offices, pincodes, buffer_km=OFFICE_BUFFER_KM):
    """(the offices whose coordinates lie in or within buffer_km of their own PIN area, {placement:
    count}); see office_placement. The rest are left out: their coordinates point somewhere else."""
    where = office_placement(offices, pincodes, buffer_km)
    counts = {p: int((where == p).sum()) for p in PLACEMENTS}
    keep = np.flatnonzero((where == "inside") | (where == "near"))
    columns = {name: [values[i] for i in keep] for name, values in offices.columns.items()}
    lat, lon = np.asarray(offices.lat)[keep], np.asarray(offices.lon)[keep]
    kept = dataclasses.replace(offices, columns=columns, lat=lat, lon=lon)
    total = len(where)
    log.info(
        "post_offices: kept %d of %d offices with usable coordinates: %d in their own PIN area (%s), "
        "%d within %g km of it; left out %d in another PIN area, %d in no PIN area (outside India or "
        "off the coast) and %d whose PIN code has no area",
        len(keep), total, counts["inside"], _share(counts["inside"], total), counts["near"], buffer_km,
        counts["elsewhere"], counts["outside"], counts["no_area"],
    )  # fmt: skip
    return kept, counts


def _share(part, total):
    return f"{part / total:.1%}" if total else "-"


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
