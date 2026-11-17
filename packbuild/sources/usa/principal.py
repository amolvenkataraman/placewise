"""OMB principal cities: delineation list 2 (registry `uscensus`, download `principal_cities`),
the Census Bureau's file of OMB Bulletin 23-01 (July 2023), public domain.

One row per principal city of every metropolitan and micropolitan statistical area, with the
city's state and place FIPS codes, which join to the cartographic place GEOID. Principal cities
can be CDPs (Paradise NV, Arlington VA, The Woodlands TX). The file lists them by state and
name, not in title order; OMB titles a CBSA by its largest principal city, then up to two more in
descending population, so `ordered` ranks them by population and the first is the one the title
leads with (barring changes since the 2020 Census).
"""

import re

from ..uscensus import read_xlsx_rows

HEADER = "CBSA Code"


def read_principal_cities(path):
    """One dict per principal city: cbsa (code), type ("metro" | "micro"), name and place (the
    7-digit GEOID). Title rows and footnotes are skipped."""
    rows = read_xlsx_rows(path)
    start = next((i for i, row in enumerate(rows) if row and row[0].strip() == HEADER), None)
    if start is None:
        raise ValueError(f"{path}: no {HEADER!r} header row")
    col = {name.strip(): i for i, name in enumerate(rows[start])}

    def get(row, name):
        i = col[name]
        return row[i].strip() if i < len(row) else ""

    out = []
    for row in rows[start + 1 :]:
        if not row or not re.fullmatch(r"\d{5}", row[0].strip()):
            continue
        kind = get(row, "Metropolitan/Micropolitan Statistical Area")
        out.append(
            {
                "cbsa": get(row, HEADER),
                "type": "metro" if kind.startswith("Metropolitan") else "micro",
                "name": get(row, "Principal City Name"),
                "place": get(row, "FIPS State Code").zfill(2) + get(row, "FIPS Place Code").zfill(5),
            }
        )
    return out


def ordered(rows, population):
    """{cbsa: [place GEOID, ...]}, largest population first (unknown last, then by name)."""
    by_cbsa = {}
    for row in rows:
        by_cbsa.setdefault(row["cbsa"], []).append(row)
    return {
        code: [
            r["place"]
            for r in sorted(
                cities, key=lambda r: (-(population.get(r["place"]) or -1), r["name"], r["place"])
            )
        ]
        for code, cities in by_cbsa.items()
    }
