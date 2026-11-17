"""OurAirports (public domain): the `airports` point layer.

Kept: every large and medium airport, plus small airports with scheduled passenger service.
Dropped: other small airfields, heliports, seaplane bases, balloon ports and closed sites.
"""

import csv
import re

from ..layer import LayerData

SOURCE = "ourairports"
ELEVATION_NULL = -32768  # i2 sentinel; real airports lie between about -1,300 and 14,500 ft
_ALWAYS = frozenset({"large_airport", "medium_airport"})
_REQUIRED = (
    "ident", "type", "name", "latitude_deg", "longitude_deg", "elevation_ft", "iso_country",
    "iso_region", "municipality", "scheduled_service", "iata_code", "gps_code",
)  # fmt: skip
_ICAO = re.compile(r"^[A-Z]{4}$")  # ICAO location indicators are four letters


def keep(row):
    return row["type"] in _ALWAYS or (row["type"] == "small_airport" and row["scheduled_service"] == "yes")


def icao(row):
    """The ICAO code: `icao_code` (newer files), else `gps_code`, else `ident`, but only when it is
    four letters; US FAA ("K00A") and Canadian ("CJV7") identifiers in those fields are not ICAO."""
    for key in ("icao_code", "gps_code", "ident"):
        value = (row.get(key) or "").strip()
        if value:
            return value if _ICAO.match(value) else ""
    return ""


def airports(csv_path):
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [name for name in _REQUIRED if name not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"{csv_path}: OurAirports header lacks {', '.join(missing)}")
        rows = [row for row in reader if keep(row)]
    columns = {
        "id": [f"ourairports:{r['ident']}" for r in rows],
        "name": [r["name"] for r in rows],
        "iata": [r["iata_code"] for r in rows],
        "icao": [icao(r) for r in rows],
        "type": [r["type"] for r in rows],
        "municipality": [r["municipality"] for r in rows],
        "country": [r["iso_country"] for r in rows],
        "region": [r["iso_region"] for r in rows],
        "scheduled": [r["scheduled_service"] == "yes" for r in rows],
        "elevation_ft": [_feet(r["elevation_ft"]) for r in rows],
    }
    types = {name: "str" for name in columns}
    types.update(scheduled="bool", elevation_ft="i2")
    return LayerData(
        "airports",
        "point",
        columns,
        (SOURCE,),
        lat=[float(r["latitude_deg"]) for r in rows],
        lon=[float(r["longitude_deg"]) for r in rows],
        types=types,
        nulls={"elevation_ft": ELEVATION_NULL},
    )


def _feet(value):
    value = value.strip()
    return round(float(value)) if value else ELEVATION_NULL
