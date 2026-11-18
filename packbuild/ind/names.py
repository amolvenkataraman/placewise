"""The curated names of Indian units and cities: placewise-data's datasets/names/ind.json (CC BY
4.0), keyed by LGD code (see the dataset's _comment for the fields).

    names = load()                      # or load(path)
    names.check(directory)              # every code is LGD's and every lgd_name still matches
    names.name("district", "62")        # "Gurugram"
    names.other_names("district", "62") # ("Gurgaon",): former names, then aliases
    names.district_aliases(directory)   # {(ISO state, folded name): district code}

India Post's directory (May 2024) still uses names LGD has since changed (Aurangabad, Osmanabad,
Ahmednagar, Hoshangabad, Ramanagara) and its own spellings (24 PARAGANAS NORTH); the former names
and aliases here match them to the current districts.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .. import datasets
from .crosswalk import folded

DATASET = datasets.path("names", "ind.json")
SOURCE = "placewise-names"
KINDS = ("state", "district", "ulb")
_UNIT = re.compile(r"^(state|district|ulb):(\d+)$")
_CITY = re.compile(r"^lgd:ulb:\d+$")


@dataclass(frozen=True)
class Names:
    units: dict  # (kind, code) -> entry
    cities: tuple
    not_neighbourhoods: tuple

    def name(self, kind, code, default=""):
        entry = self.units.get((kind, code))
        return entry["name"] if entry else default

    def other_names(self, kind, code):
        """Former names (newest rename first as listed), then aliases."""
        entry = self.units.get((kind, code)) or {}
        former = [f["name"] for f in entry.get("former", ())]
        return tuple(dict.fromkeys([*former, *entry.get("aliases", ())]))

    def district_aliases(self, directory):
        """{(ISO state, folded name): district code} for every former name and alias."""
        out = {}
        for (kind, code), _ in self.units.items():
            if kind == "district" and code in directory.districts:
                iso = directory.districts[code].iso
                for other in self.other_names(kind, code):
                    out[iso, folded(other)] = code
        return out

    def check(self, directory):
        """Raise ValueError listing codes LGD doesn't have and lgd_names that no longer match."""
        tables = {"state": directory.states, "district": directory.districts, "ulb": directory.ulbs}
        problems = []
        for (kind, code), entry in self.units.items():
            unit = tables[kind].get(code)
            if unit is None:
                problems.append(f"{kind}:{code} ({entry['name']}) is not in LGD")
            elif entry.get("lgd_name") and entry["lgd_name"] != unit.name:
                problems.append(f"{kind}:{code}: LGD now says {unit.name!r}, not {entry['lgd_name']!r}")
        if problems:
            raise ValueError(
                "datasets/names/ind.json disagrees with LGD (fix the dataset):\n  " + "\n  ".join(problems)
            )


def load(path=None):
    """The dataset, validated."""
    path = Path(path) if path is not None else DATASET
    doc = json.loads(path.read_text(encoding="utf-8"))
    units = {}
    for entry in doc.get("units", ()):
        m = _UNIT.match(entry.get("lgd", ""))
        if not m or not entry.get("name") or not _source_ok(entry.get("source")):
            raise ValueError(
                f"{path.name}: unit {entry.get('lgd')!r} needs lgd kind:code, a name and a source"
            )
        if (m.group(1), m.group(2)) in units:
            raise ValueError(f"{path.name}: {entry['lgd']} is listed twice")
        units[m.group(1), m.group(2)] = entry
    cities = tuple(doc.get("cities", ()))
    for c in cities:
        if (
            not _CITY.match(c.get("id", ""))
            or not c.get("name")
            or not c.get("lgd")
            or not _source_ok(c.get("source"))
        ):
            raise ValueError(
                f"{path.name}: city {c.get('id')!r} needs an lgd:ulb id, a name, lgd codes and a source"
            )
    return Names(units, cities, tuple(doc.get("not_neighbourhoods", ())))


def _source_ok(source):
    return (
        isinstance(source, dict)
        and bool(source.get("title"))
        and str(source.get("url", "")).startswith("https://")
    )
