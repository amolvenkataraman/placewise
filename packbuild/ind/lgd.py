"""The Local Government Directory (LGD, Ministry of Panchayati Raj; GODL-India): states,
districts, sub-districts, urban local bodies (ULBs) and the village / ULB -> PIN code tables.

lgdirectory.gov.in publishes these as daily CSV reports (the same ones data.gov.in carries under
GODL); the registry's downloads are a community mirror's monthly 7z archives of them (one CSV per
day), and the build reads the newest day of each (`sevenzip.extract_newest`). Headers, as of
October 2026:

- states: S.No., State Code, State Version, State Name (In English), State Name (In Local),
  Census 2001 Code, Census 2011 Code, State or UT
- districts: S.No., State Code, State Name (In English), District Code, District Name(In English),
  Census 2001 Code, Census 2011 Code
- subdistricts: ..., District Code, District Name, Sub-district Code, Sub-district Version,
  Sub-district Name, Census 2001 Code, Census 2011 Code
- urban_local_bodies: ..., Local Body Code, Local Body Version, Local Body Name (In English),
  Local Body Name (In Local), Localbody Type Code, Census 2011 Code
- pincode_villages: ..., District Code, District Name, SubDistrict Code, SubDistrict Name,
  Village Code, Village Name, Pincode
- pincode_urban: ..., Localbody Code, Localbody Name, Localbody Type Name, Pincode

Codes are kept as strings ("572"). Names are LGD's English names, which are title case
("Bengaluru Urban"); state codes map to ISO 3166-2 through the state names.
"""

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..fetch import fetch
from ..sources import url
from ..sources._india import text
from ..sources.indiapost import state_code
from . import sevenzip

SOURCE = "lgd-directory"
TABLES = ("states", "districts", "subdistricts", "urban_local_bodies", "pincode_villages", "pincode_urban")
_PIN = re.compile(r"^[1-9]\d{5}$")


@dataclass(frozen=True)
class Unit:
    """A state, district, sub-district or ULB."""

    code: str
    name: str
    state: str  # LGD state code ("" for states themselves)
    iso: str = ""  # ISO 3166-2 code of the state ("IN-KA")
    parent: str = ""  # a sub-district's district code
    local_name: str = ""
    census2011: str = ""
    kind: str = ""  # states: "state" / "union territory"; ULBs: their type ("Municipal Corporation")


@dataclass
class Directory:
    states: dict = field(default_factory=dict)  # code -> Unit
    districts: dict = field(default_factory=dict)
    subdistricts: dict = field(default_factory=dict)
    ulbs: dict = field(default_factory=dict)
    # pin -> Counter{(district code, sub-district code): villages}
    pin_villages: dict = field(default_factory=lambda: defaultdict(Counter))
    # pin -> {ULB code}, as LGD's pincode_urban lists them
    pin_ulbs: dict = field(default_factory=lambda: defaultdict(set))


def rows(path):
    """CSV rows as dicts with trimmed keys and values."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader, [])]
        for row in reader:
            if row:
                yield {h: text(v) for h, v in zip(header, row, strict=False)}


def _need(row, *keys, where):
    missing = [k for k in keys if k not in row]
    if missing:
        raise ValueError(f"{where}: not the LGD report expected; it lacks {', '.join(missing)}")


def read(paths):
    """A Directory from the six CSV reports: {table name: path} (TABLES)."""
    d = Directory()
    for r in _checked(paths["states"], "State Code", "State Name (In English)", "State or UT"):
        iso = state_code(r["State Name (In English)"])
        kind = "union territory" if r["State or UT"].upper() == "U" else "state"
        d.states[r["State Code"]] = Unit(
            r["State Code"],
            r["State Name (In English)"],
            "",
            iso,
            local_name=r.get("State Name (In Local)", ""),
            census2011=r.get("Census 2011 Code", ""),
            kind=kind,
        )
    iso_of = {code: s.iso for code, s in d.states.items()}
    for r in _checked(paths["districts"], "State Code", "District Code", "District Name(In English)"):
        st = r["State Code"]
        d.districts[r["District Code"]] = Unit(
            r["District Code"],
            r["District Name(In English)"],
            st,
            iso_of.get(st, ""),
            census2011=r.get("Census 2011 Code", ""),
        )
    for r in _checked(
        paths["subdistricts"], "State Code", "District Code", "Sub-district Code", "Sub-district Name"
    ):
        st = r["State Code"]
        d.subdistricts[r["Sub-district Code"]] = Unit(
            r["Sub-district Code"],
            r["Sub-district Name"],
            st,
            iso_of.get(st, ""),
            parent=r["District Code"],
            census2011=r.get("Census 2011 Code", ""),
        )
    types = Counter()
    pin_urban = list(_checked(paths["pincode_urban"], "Localbody Code", "Localbody Type Name", "Pincode"))
    for r in pin_urban:
        types[r["Localbody Code"], _type_name(r["Localbody Type Name"])] += 1
    type_of = {}
    for (code, name), _ in types.most_common():
        type_of.setdefault(code, name)
    for r in _checked(
        paths["urban_local_bodies"], "State Code", "Local Body Code", "Local Body Name (In English)"
    ):
        st, code = r["State Code"], r["Local Body Code"]
        d.ulbs[code] = Unit(
            code,
            r["Local Body Name (In English)"],
            st,
            iso_of.get(st, ""),
            local_name=r.get("Local Body Name (In Local)", ""),
            census2011=_census(r.get("Census 2011 Code", "")),
            kind=type_of.get(code, ""),
        )
    for r in _checked(paths["pincode_villages"], "District Code", "SubDistrict Code", "Pincode"):
        if _PIN.match(r["Pincode"]):
            d.pin_villages[r["Pincode"]][r["District Code"], r["SubDistrict Code"]] += 1
    for r in pin_urban:
        if _PIN.match(r["Pincode"]) and r["Localbody Code"] in d.ulbs:
            d.pin_ulbs[r["Pincode"]].add(r["Localbody Code"])
    return d


def _checked(path, *keys):
    first = True
    for r in rows(path):
        if first:
            _need(r, *keys, where=Path(path).name)
            first = False
        yield r


def _type_name(name):
    """LGD's ULB type spellings vary ("MUNICIPALITY", "Nagar Panchayat\\t"): trimmed, title case."""
    name = " ".join(name.split())
    return name.title() if name.isupper() else name


def _census(code):
    return "" if code in ("", "0") else code


def download(cache_dir, refresh=False):
    """{table: extracted CSV path}: each table's registry download (a monthly 7z) fetched into
    <cache_dir>/lgd/ and its newest daily CSV extracted beside it once."""
    folder = Path(cache_dir) / "lgd"
    out = {}
    for table in TABLES:
        archive = fetch(url(SOURCE, table), folder, refresh=refresh)
        out[table] = sevenzip.extract_newest(archive, folder / archive.name.removesuffix(".7z"))
    return out
