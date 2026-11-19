"""The size rules of docs/code-structure.md, on every module of the library, packbuild and the tests:
a module stays under MAX_LINES lines (generated data modules excepted), and a package holds at most
MAX_MODULES modules, subpackages grouping the rest by subject."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAX_LINES = 400
MAX_MODULES = 8
# where modules live; test folders mirror src/ and packbuild/ and are not packages, so only their
# modules' size is checked
LIBRARY = ("src/placewise", "packbuild")
EVERYWHERE = (*LIBRARY, "tests")
# a package's `__init__.py` and `python -m` entry point don't count as modules
NOT_MODULES = frozenset(("__init__.py", "__main__.py"))
# packages wider than MAX_MODULES, and why grouping them would break something users rely on
WIDE = {
    "packbuild": "each pack's build is a command, `python -m packbuild.<name>`, documented and scripted",
    "src/placewise/constants": "one module per subject, each a public path (placewise.constants.wgs84)",
    "src/placewise/geo": "every module is a public path (placewise.geo.distances, .shapes, .polylines)",
    "src/placewise/io": "every format's module is a public path (placewise.io.gpx, .fit, .shapefile)",
    "src/placewise/model": "its modules are public paths (placewise.model.places, .privacy, .presence)",
}


def _modules(base):
    return sorted(p for p in (ROOT / base).rglob("*.py") if "__pycache__" not in p.parts)


def _generated(text):
    """Generated data modules say so in their first line ("GENERATED ... do not edit")."""
    first = text.split("\n", 1)[0]
    return "GENERATED" in first and "do not edit" in text[:500]


def _packages():
    found = {}
    for base in LIBRARY:
        for path in _modules(base):
            if path.name not in NOT_MODULES:
                found.setdefault(path.parent.relative_to(ROOT).as_posix(), []).append(path.name)
    return found


@pytest.mark.parametrize("base", EVERYWHERE)
def test_modules_stay_under_the_line_limit(base):
    long = {}
    for path in _modules(base):
        text = path.read_text(encoding="utf-8")
        lines = len(text.splitlines())
        if lines > MAX_LINES and not _generated(text):
            long[path.relative_to(ROOT).as_posix()] = lines
    assert not long, f"over {MAX_LINES} lines, split by responsibility: {long}"


def test_packages_hold_at_most_eight_modules():
    wide = {
        package: len(names)
        for package, names in _packages().items()
        if len(names) > MAX_MODULES and package not in WIDE
    }
    assert not wide, f"over {MAX_MODULES} modules, group them into subpackages: {wide}"


def test_every_wide_package_still_needs_its_exemption():
    packages = _packages()
    stale = [p for p in WIDE if len(packages.get(p, ())) <= MAX_MODULES]
    assert not stale, f"no longer over {MAX_MODULES} modules, drop from WIDE: {stale}"
