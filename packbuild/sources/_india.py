"""Shared by the India loaders: ISO 3166-2:IN codes and the WGS84 check for GeoJSON input."""

import json
import re
from pathlib import Path

from placewise.io import read_geojson

# ISO 3166-2:IN after the 2023-11-23 change (CT->CG, OR->OD, TG->TS, UT->UK): code -> English name
ISO_NAMES = {
    "IN-AN": "Andaman and Nicobar Islands", "IN-AP": "Andhra Pradesh", "IN-AR": "Arunachal Pradesh",
    "IN-AS": "Assam", "IN-BR": "Bihar", "IN-CH": "Chandigarh", "IN-CG": "Chhattisgarh",
    "IN-DH": "Dadra and Nagar Haveli and Daman and Diu", "IN-DL": "Delhi", "IN-GA": "Goa",
    "IN-GJ": "Gujarat", "IN-HR": "Haryana", "IN-HP": "Himachal Pradesh", "IN-JK": "Jammu and Kashmir",
    "IN-JH": "Jharkhand", "IN-KA": "Karnataka", "IN-KL": "Kerala", "IN-LA": "Ladakh",
    "IN-LD": "Lakshadweep", "IN-MP": "Madhya Pradesh", "IN-MH": "Maharashtra", "IN-MN": "Manipur",
    "IN-ML": "Meghalaya", "IN-MZ": "Mizoram", "IN-NL": "Nagaland", "IN-OD": "Odisha",
    "IN-PY": "Puducherry", "IN-PB": "Punjab", "IN-RJ": "Rajasthan", "IN-SK": "Sikkim",
    "IN-TN": "Tamil Nadu", "IN-TS": "Telangana", "IN-TR": "Tripura", "IN-UP": "Uttar Pradesh",
    "IN-UK": "Uttarakhand", "IN-WB": "West Bengal",
}  # fmt: skip

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
