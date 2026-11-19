"""Shared by the India loaders: ISO 3166-2:IN codes and the WGS84 check for GeoJSON input."""

import json
import re
from pathlib import Path

from placewise.constants.countries.ind.subregions import SUBREGIONS
from placewise.io import read_geojson

# ISO 3166-2:IN code -> English name, from the package's table (constants/countries/ind/subregions.py,
# which documents the 2023-11-23 change: CT->CG, OR->OD, TG->TS, UT->UK)
ISO_NAMES = {state.iso: state.name for state in SUBREGIONS}

# GeoJSON "crs" names that mean WGS84 longitude/latitude (RFC 7946 drops the member: absent = WGS84)
_WGS84_CRS = re.compile(r"(CRS:?84|EPSG:+4326)$", re.IGNORECASE)


def normalise_name(name):
    """Upper case, "&" spelled "and", a leading "THE" and repeated spaces dropped."""
    name = re.sub(r"\s+", " ", name.replace("&", " and ")).strip().upper()
    return name[4:] if name.startswith("THE ") else name


def read_wgs84_geojson(path):
    """read_geojson, refusing files whose "crs" member names anything but WGS84 lon/lat. Some
    government files carry projected metres (e.g. EPSG:7755) in GeoJSON; placewise doesn't reproject."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    crs = ((data.get("crs") or {}).get("properties") or {}).get("name")
    if crs and not _WGS84_CRS.search(crs.strip()):
        raise ValueError(
            f"{path.name}: coordinates are in {crs}, not WGS84 longitude/latitude; not reprojected"
        )
    return read_geojson(data)


def text(value):
    """Clean text: None -> "", surrounding whitespace and NUL padding trimmed."""
    return "" if value is None else str(value).strip(" \t\r\n\x00")
