"""Shared helpers for end-to-end tests: real built packs, public places only.

Packs are found in $PLACEWISE_E2E_PACKS, else the repo's .cache/packbuild/out/ (where packbuild
writes them). The newest `<name>-<version>` directory wins. A test that needs a pack which isn't
built is skipped, never failed: build it with `uv run python -m packbuild.<builder>`.

Country packs are looked up by their alpha-3 name first and their older alpha-2 name second
(`ind`, then `in`), so the tests survive the pack-name change.
"""

import os
from functools import cache
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OLD_NAMES = {"usa": "us", "can": "ca", "ind": "in"}


def packs_dir():
    return Path(os.environ.get("PLACEWISE_E2E_PACKS") or REPO / ".cache" / "packbuild" / "out")


def pack_path(name):
    """The newest built pack directory for `name`, or None."""
    root = packs_dir()
    for candidate in (name, OLD_NAMES.get(name)):
        if candidate is None:
            continue
        found = sorted(p for p in root.glob(f"{candidate}-*") if (p / "pack.json").is_file())
        if found:
            return found[-1]
    return None


def require_packs(*names):
    """Pack directories for `names`, skipping the calling test if any isn't built."""
    paths = [pack_path(n) for n in names]
    missing = [n for n, p in zip(names, paths, strict=True) if p is None]
    if missing:
        pytest.skip(f"packs not built: {', '.join(missing)} (in {packs_dir()})")
    return paths


@cache
def geocoder(*names):
    """A Geocoder over the named packs (cached per combination)."""
    from placewise.engine import Geocoder

    return Geocoder(packs=require_packs(*names))
