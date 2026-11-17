"""Canadian Geographical Names Database (Natural Resources Canada, OGL-Canada 2.0; registry
`nrcan-cgndb`): the Canada pack's `populated_places` point layer.

The national CSV (cgn_canada_csv_eng.zip, about 366,000 official names, refreshed weekly) holds
lakes, peaks and parks too; the layer keeps generic category "Populated Place": hamlets (Lake
Louise in Improvement District No. 9), rural communities (Field BC), towns, and the urban
communities, neighbourhoods and boroughs inside amalgamated cities (Scarborough, Kanata, Malton,
Port Credit, Ville-Marie). Railway points, post offices, stations and former or vacated places are
dropped: they are names on a map, not places people live. Which of the rest name a locality or a
sublocality is the naming rules' choice (placewise.constants.naming).

Columns: id ("cgndb:<CGNDB ID>"), name (the official name as decided, English or French, not
translated), generic (the generic term: "Hamlet", "Urban Community"), province (SGC alpha code),
scale ("Relevance at Scale": the map scale from which the name is shown, e.g. 145000 for a
neighbourhood, 1200000 for Scarborough; a ready-made prominence). Coordinates are NAD83, used as
WGS84 (1-2 m apart in Canada).
"""

import csv
import io
import zipfile

from ...layer import LayerData

SOURCE = "nrcan-cgndb"
CATEGORY = "Populated Place"
# generic terms of populated places that are not settlements or neighbourhoods
DROPPED = frozenset(
    {
        "Railway Point", "Railway Stop", "Railway Junction", "Railway Yard", "Former Railway Point",
        "Post Office", "Former Post Office", "Military Post Office", "Station", "Metro Station",
        "REM Station", "Research Station", "Weather Station", "Customs Point",
        "Vacated or Seasonal Settlement",
        "Former Locality", "Abandoned Locality", "Former First Nation Village", "Industrial Park",
        "Industrial Area", "Ski Area", "Trading Post", "Ranch", "Fort", "Landing",
    }
)  # fmt: skip
PROVINCES = {
    "Newfoundland and Labrador": "NL", "Prince Edward Island": "PE", "Nova Scotia": "NS",
    "New Brunswick": "NB", "Quebec": "QC", "Ontario": "ON", "Manitoba": "MB", "Saskatchewan": "SK",
    "Alberta": "AB", "British Columbia": "BC", "Yukon": "YT", "Northwest Territories": "NT", "Nunavut": "NU",
}  # fmt: skip
SCALE_NULL = -1
_COLUMNS = ("CGNDB ID", "Geographical Name", "Generic Term", "Generic Category", "Latitude", "Longitude",
            "Province - Territory", "Relevance at Scale")  # fmt: skip


def read_rows(archive):
    """The CSV rows (dicts) of the zipped national file."""
    with zipfile.ZipFile(archive) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        text = io.TextIOWrapper(z.open(name), encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text)
        missing = [c for c in _COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"{archive}: no column(s) {', '.join(missing)}")
        yield from reader


def populated_places(archive):
    """The `populated_places` point layer, in file order (alphabetical by name)."""
    rows = [
        r
        for r in read_rows(archive)
        if r["Generic Category"] == CATEGORY and r["Generic Term"] not in DROPPED
    ]
    scale = [int(r["Relevance at Scale"]) if r["Relevance at Scale"].strip() else SCALE_NULL for r in rows]
    columns = {
        "id": [f"cgndb:{r['CGNDB ID']}" for r in rows],
        "name": [r["Geographical Name"].strip() for r in rows],
        "generic": [r["Generic Term"].strip() for r in rows],
        "province": [PROVINCES.get(r["Province - Territory"], "") for r in rows],
        "scale": scale,
    }
    types = {name: "str" for name in columns}
    types["scale"] = "i8"
    return LayerData(
        "populated_places", "point", columns, (SOURCE,),
        lat=[float(r["Latitude"]) for r in rows], lon=[float(r["Longitude"]) for r in rows],
        types=types, nulls={"scale": SCALE_NULL},
    )  # fmt: skip
