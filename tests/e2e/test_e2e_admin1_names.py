"""The world pack's admin-1 names in English, with the local name kept for search and Natural
Earth's region of each unit (packbuild.sources.naturalearth.admin1). Public places only; skipped
for world packs built before the English names (2026.11.1)."""

import pytest
from e2e_kit import geocoder, require_packs

from placewise.packs import open_pack


@pytest.fixture(scope="module")
def world():
    (path,) = require_packs("world")
    pack = open_pack(path)
    if "name_local" not in pack["admin1"].fields:
        pytest.skip(f"{path.name} was built before the English admin-1 names")
    return pack


@pytest.fixture(scope="module")
def geo(world):
    return geocoder("world")


@pytest.mark.parametrize(
    ("point", "admin1"),
    [
        ((52.3731, 4.8926), "North Holland"),  # Amsterdam, Dam Square
        ((50.9375, 6.9603), "North Rhine-Westphalia"),  # Cologne Cathedral
        ((48.2082, 16.3738), "Vienna"),
        ((48.5394, 2.6608), "Seine-et-Marne"),  # Melun, a Paris suburb: Natural Earth's typo fixed
        ((30.5085, 47.7804), "Basra"),
    ],
)
def test_admin1_is_english(geo, point, admin1):
    assert geo.lookup(*point).admin1.name == admin1


def test_france_keeps_its_departments_with_their_region_as_data(geo, world):
    r = geo.lookup(48.5394, 2.6608)  # Melun
    assert r.admin1.id == "iso:FR-77"
    layer = world["admin1"]
    row = layer.find("id", "iso:FR-77")[0]
    assert (layer.value("region", row), layer.value("region_code", row)) == ("Île-de-France", "FR-IDF")


def test_local_names_still_find_the_unit(geo):
    assert geo.find("Nordrhein-Westfalen")[0].place.id == "iso:DE-NW"
    assert geo.find("Noord-Holland")[0].place.id == "iso:NL-NH"
