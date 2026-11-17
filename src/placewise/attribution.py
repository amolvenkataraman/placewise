"""The source registry: one JSON file per purpose in `sources/` (boundaries.json, places.json,
postal.json ...), each listing, per region (`world`, or a country's lower-case ISO 3166-1 alpha-3
code: `usa`, `can`, `ind` ...), the sources used for that purpose there, with their attribution
and that purpose's download URLs. A region's sources go in the pack of the same name (or `world`).

Organising by purpose shows at a glance what each region is covered with, and where it isn't (a
file's `gaps` says why a region has nothing). A source used for several purposes appears in each
file; `load_sources` merges those entries into one `model.Source` (the licence gate) and refuses a
source credited differently in two places. ATTRIBUTION.md and `placewise attribution` are generated
from here, and the build takes every download URL from here.
"""

import json
from dataclasses import replace
from functools import cache
from pathlib import Path

from placewise.constants.countries.countries import BY_ALPHA3
from placewise.model import Source

SOURCES_DIR = Path(__file__).with_name("sources")
# what identifies a source; every entry for it must agree on these
_IDENTITY = ("name", "url", "licence", "credit", "derived_database")


def load_registry(folder=None):
    """{purpose: {region: (Source, ...)}}, each Source holding only that purpose's downloads."""
    return _shipped()[0] if _is_shipped(folder) else _load(Path(folder))[0]


def load_gaps(folder=None):
    """{purpose: {region: why there is no source}}."""
    return _shipped()[1] if _is_shipped(folder) else _load(Path(folder))[1]


def load_sources(folder=None):
    """{id: Source} with each source's entries merged across purposes and regions."""
    return _shipped()[2] if _is_shipped(folder) else _load(Path(folder))[2]


def source(source_id):
    """One shipped source by id; KeyError names the id if no purpose file lists it."""
    try:
        return _shipped()[2][source_id]
    except KeyError:
        raise KeyError(f"no source {source_id!r} in {SOURCES_DIR}") from None


def _is_shipped(folder):
    return folder is None or Path(folder) == SOURCES_DIR


@cache
def _shipped():
    return _load(SOURCES_DIR)


def _load(folder):
    registry, gaps, merged = {}, {}, {}
    for path in sorted(folder.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        purpose = doc.get("purpose")
        if purpose != path.stem:
            raise ValueError(f"{path.name} says purpose {purpose!r}; the file must be named {purpose}.json")
        unknown = set(doc) - {"purpose", "description", "regions", "gaps"}
        if unknown or not doc.get("description"):
            raise ValueError(f"{path.name}: needs a description; unknown keys {sorted(unknown)}")
        registry[purpose] = {}
        for region, entries in doc.get("regions", {}).items():
            if not _is_region(region):
                raise ValueError(
                    f"{path.name}: region {region!r} is not 'world' or a lower-case ISO 3166-1 alpha-3 code"
                )
            where = f"{path.name} [{region}]"
            registry[purpose][region] = tuple(_entry(item, where) for item in entries)
            for item in registry[purpose][region]:
                merged[item.id] = _merge(merged.get(item.id), item, where)
        gaps[purpose] = dict(doc.get("gaps", {}))
    return registry, gaps, merged


def _is_region(region):
    return region == "world" or (region.islower() and region.upper() in BY_ALPHA3)


def _entry(item, where):
    try:
        return Source.from_dict(item)
    except (TypeError, ValueError, KeyError) as e:
        raise ValueError(f"{where}: {e}") from None


def _merge(known, item, where):
    if known is None:
        return item
    for name in _IDENTITY:
        if getattr(known, name) != getattr(item, name):
            raise ValueError(f"{where}: source {item.id!r} gives a different {name} than elsewhere")
    downloads = dict(known.downloads)
    for key, url in item.downloads.items():
        if downloads.setdefault(key, url) != url:
            raise ValueError(f"{where}: source {item.id!r} download {key!r} has two different URLs")
    notes = [n for n in dict.fromkeys((known.notes, item.notes)) if n]
    return replace(
        known,
        downloads=downloads,
        used_in=tuple(dict.fromkeys((*known.used_in, *item.used_in))),
        notes="\n\n".join(notes) or None,
    )


_TITLE = "# Data attribution"

# the first paragraph of every attribution file; DISCLAIMER.md sits beside each one (the repo root,
# every data release)
DISCLAIMER = """\
**Disclaimer.** placewise and its data packs are provided "as is" and "where is", without warranty
of any kind and with no legal liability for their use. The data may be wrong, incomplete or out of
date, and is not an official determination of any place's name, boundaries or status. See
[DISCLAIMER.md](DISCLAIMER.md).
"""

_INTRO = """\
Generated from the source registry (`src/placewise/sources/`) by `placewise attribution --all`; do
not edit by hand. It lists every dataset placewise data packs are built from, with its licence and
the credit line to show. An app that ships or displays placewise data can link to this file, and
should still read each licence for its own obligations.
"""

_SUBSET_INTRO = """\
The datasets {subject} are built from, with each one's licence and the credit line to show,
generated from placewise's source registry. placewise's own ATTRIBUTION.md lists every source it
uses. An app that ships or displays this data should still read each licence for its own
obligations.
"""


def render_markdown(sources=None, registry=None, gaps=None, only=None, subject=None):
    """ATTRIBUTION.md: the disclaimer, a summary table, coverage by purpose and region, then each
    source's credit line, licence and notes. `only` (source ids) narrows it to those sources and the
    regions they serve, for a data release or the installed packs, which `subject` names (default
    "the data packs published with this file"); an unknown id is a KeyError."""
    sources = load_sources() if sources is None else sources
    registry = load_registry() if registry is None else registry
    gaps = load_gaps() if gaps is None else gaps
    intro = _INTRO
    if only is not None:
        sources, registry, gaps = _subset(set(only), sources, registry, gaps)
        intro = _SUBSET_INTRO.format(subject=subject or "the data packs published with this file")
    lines = [_TITLE, "", DISCLAIMER, intro, "| Source | Licence | Used in |", "|---|---|---|"]
    for s in sources.values():
        lines.append(f"| [{s.name}]({s.url}) | {s.licence} | {', '.join(s.used_in) or '-'} |")
    lines += ["", "## Coverage", "", "| Purpose | Region | Sources |", "|---|---|---|"]
    for purpose, regions in registry.items():
        for region in sorted({*regions, *gaps.get(purpose, {})}, key=lambda r: (r != "world", r)):
            names = ", ".join(s.name for s in regions.get(region, ())) or f"none: {gaps[purpose][region]}"
            lines.append(f"| {purpose} | {region} | {names} |")
    for s in sources.values():
        lines += ["", f"## {s.name}", "", f"- Credit: {s.credit}", f"- Licence: {s.licence}"]
        lines.append(f"- Website: {s.url}")
        if s.share_alike:
            lines.append("- Share-alike: shipped only in the separate share-alike pack.")
        if s.derived_database:
            lines.append(f"- Derived database offered at: {s.derived_database}")
        if s.notes:
            lines += ["", s.notes]
    return "\n".join(lines) + "\n"


def render_credits(sources=None, only=None):
    """Each source's credit line, one per line, in registry order; `only` (source ids) narrows it
    to those sources, and an unknown id is a KeyError."""
    sources = load_sources() if sources is None else sources
    if only is not None:
        sources = _known(set(only), sources)
    return "".join(f"{s.credit}\n" for s in sources.values())


def pack_sources(packs):
    """The source ids a set of packs (anything with `.sources`) carries, in order, each once."""
    return tuple(dict.fromkeys(s for pack in packs for s in pack.sources))


def _known(ids, sources):
    if unknown := sorted(ids - set(sources)):
        raise KeyError(f"no source(s) {', '.join(unknown)} in the registry")
    return {k: s for k, s in sources.items() if k in ids}


def _subset(ids, sources, registry, gaps):
    sources = _known(ids, sources)
    registry = {
        purpose: {r: kept for r, ss in regions.items() if (kept := tuple(s for s in ss if s.id in ids))}
        for purpose, regions in registry.items()
    }
    served = {r for regions in registry.values() for r in regions}
    gaps = {purpose: {r: why for r, why in g.items() if r in served} for purpose, g in gaps.items()}
    return sources, registry, gaps
