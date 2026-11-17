"""Shared helpers for end-to-end tests: real built packs, public places only.

Packs are found in $E2E_PACKS_DIR, else where packbuild writes them (`packbuild.fetch.DEFAULT_CACHE`
/ "out", i.e. ~/.placewise/packbuild/out unless $PACKBUILD_CACHE says otherwise). The newest
`<name>-<version>` directory wins. A test that needs a pack which isn't built is skipped, never
failed: build it with `uv run python -m packbuild.<builder>`.

The variable is deliberately not PLACEWISE_*: placewise's config loader rejects unknown
PLACEWISE_* variables.
"""

import os
from functools import cache
from pathlib import Path

import pytest

ENV_PACKS_DIR = "E2E_PACKS_DIR"


def packs_dirs():
    if os.environ.get(ENV_PACKS_DIR):
        return [Path(os.environ[ENV_PACKS_DIR])]
    from packbuild.fetch import DEFAULT_CACHE

    return [DEFAULT_CACHE / "out"]


def pack_path(name):
    """The newest built pack directory for `name`, or None."""
    for root in packs_dirs():
        found = sorted(p for p in root.glob(f"{name}-*") if (p / "pack.json").is_file())
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


@cache
def geocoder(*names):
    """A Geocoder over the named packs (cached per combination)."""
    from placewise.engine import Geocoder

    return Geocoder(packs=require_packs(*names))
