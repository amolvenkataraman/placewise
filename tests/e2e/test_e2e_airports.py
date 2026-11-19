"""Result.airport on the world pack: AT by the airport's size, NEAR by size and scheduled service
(docs/naming.md, "Airports"). Public places only."""

import pytest
from e2e_kit import geocoder, require_packs

from placewise.packs import open_pack


@pytest.fixture(scope="module")
def geo():
    (path,) = require_packs("world")
    fields = open_pack(path)["airports"].fields
    if "type" not in fields or "scheduled" not in fields:
        pytest.skip(f"{path.name} has no airport type or scheduled service")
    return geocoder("world")


CASES = [
    # name, point, IATA, relation
    ("HYD terminal", (17.2403, 78.4294), "HYD", "at"),
    ("Begumpet's runway: at BPM, though it has no airline service", (17.4531, 78.4676), "BPM", "at"),
    ("Hussain Sagar, 3 km from Begumpet: HYD, not BPM", (17.4239, 78.4738), "HYD", "near"),
    ("Hillsdale, San Mateo, 5 km from San Carlos: SFO, not SQL", (37.5375, -122.3005), "SFO", "near"),
    ("SFO's terminals", (37.6155, -122.3900), "SFO", "at"),
    ("Toronto Pearson", (43.6777, -79.6248), "YYZ", "at"),
    ("Billy Bishop's terminal", (43.6281, -79.3960), "YTZ", "at"),
    ("Harbourfront, 1.6 km from Billy Bishop: near it, not at it", (43.6387, -79.3817), "YTZ", "near"),
    ("Union Station, Toronto", (43.6453, -79.3806), "YTZ", "near"),
    ("CN Tower: Billy Bishop at 1.8 km beats Pearson at 23 km", (43.6426, -79.3871), "YTZ", "near"),
    ("Mumbai, Bandra Kurla Complex", (19.0660, 72.8700), "BOM", "near"),
]


@pytest.mark.parametrize(("name", "point", "iata", "relation"), CASES, ids=[c[0] for c in CASES])
def test_airport(geo, name, point, iata, relation):
    r = geo.lookup(*point)
    assert (r.airport.place.codes["iata"], r.airport.relation.value) == (iata, relation)


def test_a_large_airport_reaches_farther_than_ten_km(geo):
    r = geo.lookup(17.4474, 78.3762)  # HITEC City, 25 km from HYD
    assert r.airport.place.codes["iata"] == "HYD" and 20 < r.airport.distance_km < 30
