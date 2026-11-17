"""The source registry: every dataset placewise uses is one JSON file in `sources/`, named after its id.

Keeping sources as data, not code, means the attribution an app has to show can be read, linked
to and generated (ATTRIBUTION, `placewise attribution`) from one place, and the build takes every
download URL from here. Loading a file constructs a `model.Source`, which is the licence gate.
"""

import json
from functools import cache
from pathlib import Path

from placewise.model import Source

SOURCES_DIR = Path(__file__).with_name("sources")


def load_sources(folder=None):
    """{id: Source} for every *.json in `folder` (default: the shipped registry)."""
    folder = Path(folder) if folder is not None else SOURCES_DIR
    if folder == SOURCES_DIR:
        return _shipped()
    return _load(folder)


def source(source_id):
    """One shipped source by id; KeyError names the id if there's no such file."""
    try:
        return _shipped()[source_id]
    except KeyError:
        raise KeyError(f"no source {source_id!r} in {SOURCES_DIR}") from None


@cache
def _shipped():
    return _load(SOURCES_DIR)


def _load(folder):
    sources = {}
    for path in sorted(folder.glob("*.json")):
        item = Source.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if item.id != path.stem:
            raise ValueError(f"{path.name} holds source {item.id!r}; the file must be named {item.id}.json")
        sources[item.id] = item
    return sources
