"""Shared helpers for end-to-end tests: real built packs, public places only.

Packs are found in $E2E_PACKS_DIR, else where packbuild writes them (`packbuild.fetch.DEFAULT_CACHE`
/ "out", i.e. ~/.placewise/packbuild/out unless $PACKBUILD_CACHE says otherwise). The newest
`<name>-<version>` directory wins. A test that needs a pack which isn't built is skipped, never
failed: build it with `uv run python -m packbuild.<builder>`.

The variable is deliberately not PLACEWISE_*: placewise's config loader rejects unknown
PLACEWISE_* variables.
"""

import os
from functools import lru_cache
from pathlib import Path

import pytest

ENV_PACKS_DIR = "E2E_PACKS_DIR"


def packs_dirs():
    if os.environ.get(ENV_PACKS_DIR):
        return [Path(os.environ[ENV_PACKS_DIR])]
    from packbuild.fetch import DEFAULT_CACHE

    return [DEFAULT_CACHE / "out"]


def pack_path(name):
    """The newest built pack directory for `name`, or None ("world" never picks "world-water")."""
    from placewise.store.paths import parse_pack_dir

    for root in packs_dirs():
        found = sorted(
            p
            for p in root.glob(f"{name}-*")
            if (p / "pack.json").is_file() and (parse_pack_dir(p.name) or ("",))[0] == name
        )
        if found:
            return found[-1]
    return None


def require_packs(*names):
    """Pack directories for `names`, skipping the calling test if any isn't built."""
    paths = [pack_path(n) for n in names]
    missing = [n for n, p in zip(names, paths, strict=True) if p is None]
    if missing:
        looked = ", ".join(str(d) for d in packs_dirs())
        pytest.skip(f"packs not built: {', '.join(missing)} (looked in {looked})")
    return paths


# what the naming rules read from each country pack beyond the boundaries: (layer, column or None);
# a pack built before them is skipped, not failed (rebuild it with packbuild)
NAMING_DATA = {
    "usa": [("postal_cities|zcta", "postal_place"), ("cbsa", "principal_cities")],
    "can": [("populated_places", None)],
    "ind": [("states", None), ("districts", None), ("cities", None), ("neighbourhoods", None)],
}


def require_naming_data(*names):
    """Skip the calling test if a pack named here predates the naming data it needs."""
    from placewise.packs import open_pack

    for name, path in zip(names, require_packs(*names), strict=True):
        pack = open_pack(path)
        for layers, column in NAMING_DATA.get(name, ()):
            layer = next((x for x in layers.split("|") if x in pack), None)  # "a|b": either will do
            if layer is None or (column and column not in pack[layer].fields):
                pytest.skip(f"{path.name} has no {layers}{'.' + column if column else ''}: rebuild it")


def with_zip(names):
    """`names` with usa-zip after usa when the usa pack's ZIP Code areas are a pack of their own
    (packs built before it have them in usa); skips the calling test if usa-zip isn't built."""
    from placewise.packs import open_pack

    if "usa" not in names or "zcta" in open_pack(require_packs("usa")[0]):
        return tuple(names)
    require_packs("usa-zip")
    at = names.index("usa") + 1
    return (*names[:at], "usa-zip", *names[at:])


def optional(*names):
    """Those of `names` that are built (optional packs a test reads when they are there)."""
    return tuple(n for n in names if pack_path(n) is not None)


def us_parks():
    """The US park packs: usa-parks, and usa-parks-local (city and county parks) when built."""
    return ("usa-parks", *optional("usa-parks-local"))


def naming_geocoder():
    """A Geocoder over the world, US (with its ZIP Codes), Canada and India packs, with their
    naming data."""
    names = ("world", "usa", "can", "ind")
    require_naming_data(*names)
    return geocoder(*with_zip(names))


# Only the two most recent combinations stay open: each Geocoder maps several packs, and keeping
# every combination alive made the e2e suite exceed the machine's memory budget.
@lru_cache(maxsize=2)
def geocoder(*names):
    """A Geocoder over the named packs (cached per combination)."""
    from placewise.engine import Geocoder

    return Geocoder(packs=require_packs(*names))
