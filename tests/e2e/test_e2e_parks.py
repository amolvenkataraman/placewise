"""Parks on the real packs (usa-parks, can-parks, world-parks): public places only.

Skipped when a pack isn't built (`uv run python -m packbuild.parks usa can world`).
"""

import pytest
from e2e_kit import geocoder

from placewise.model import PlaceKind


def within(packs, lat, lon):
    return [p.name for p in geocoder(*packs).lookup(lat, lon).within]


def near_parks(packs, lat, lon):
    return {
        n.place.name: n.distance_km
        for n in geocoder(*packs).lookup(lat, lon).near
        if n.place.kind == PlaceKind.PARK
    }


@pytest.mark.parametrize(
    ("pack", "point", "park"),
    [
        ("usa-parks", (37.7456, -119.5936), "Yosemite National Park"),  # Yosemite Valley
        ("usa-parks", (40.7829, -73.9654), "Central Park"),  # Central Park, New York
        ("can-parks", (51.4254, -116.1773), "Banff National Park"),  # Lake Louise
        pytest.param(
            "can-parks",
            (43.82, -79.17),
            "Rouge National Urban Park",
            marks=pytest.mark.xfail(reason="the 2026.11 build's Rouge outline misses points inside it: open"),
        ),  # Rouge Park, Toronto
    ],
)
def test_within(pack, point, park):
    found = within(("world", pack), *point)
    assert found and found[0] == park if pack == "can-parks" else park in found


@pytest.mark.parametrize(
    ("point", "park"),
    [((29.5300, 78.7747), "Jim Corbett National Park"), ((26.5775, 93.1711), "Kaziranga National Park")],
)
def test_india_parks_are_near_never_within(point, park):
    assert within(("world", "world-parks"), *point) == []
    assert park in near_parks(("world", "world-parks"), *point)
