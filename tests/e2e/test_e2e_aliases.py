"""The names people type, as built into the real world pack: alias columns on cities, admin1 and
countries, and the city each airport serves. Public places only; skipped when the world pack isn't
built, or was built before these columns."""

from functools import cache

import pytest
from e2e_kit import require_packs

from placewise.packs import open_pack


@cache
def _world():
    (path,) = require_packs("world")
    pack = open_pack(path)
    if "aliases" not in pack["cities"].fields or "served_city" not in pack["airports"].fields:
        pytest.skip(f"{path.name} was built before the alias columns")
    return pack


def _row(layer, ident):
    layer = _world()[layer]
    return layer.row(int(layer.find("id", ident)[0]))


def _names(row, column):
    return set(filter(None, (row[column] or "").split("|")))


@pytest.mark.parametrize(
    ("ident", "column", "expected"),
    [
        ("geonames:6167865", "airport_codes", {"YYZ"}),  # Toronto
        ("geonames:6167865", "abbreviations", {"TOR"}),
        ("geonames:1264527", "former_names", {"Madras"}),  # Chennai
        ("geonames:1275004", "former_names", {"Calcutta"}),  # Kolkata
        ("geonames:1277333", "former_names", {"Bangalore"}),  # Bengaluru
        ("geonames:1277333", "airport_codes", {"BLR"}),
        ("geonames:1253102", "aliases", {"Vizag"}),  # Visakhapatnam
        ("geonames:5128581", "abbreviations", {"NYC"}),  # New York City
    ],
)
def test_city_aliases(ident, column, expected):
    assert expected <= _names(_row("cities", ident), column)


def test_suppressed_and_noisy_names_stay_out():
    kochi = _row("cities", "geonames:1273874")
    every = set().union(*(_names(kochi, c) for c in ("aliases", "abbreviations", "former_names")))
    assert "Cochin" in every and not {"Ernakulam", "Fort Cochin"} & every
    nyc = _row("cities", "geonames:5128581")
    assert not {"Big Apple", "New Amsterdam"} & _names(nyc, "aliases")  # a nickname, an uncurated old name


def test_admin1_and_country_aliases():
    assert "Orissa" in _names(_row("admin1", "iso:IN-OR"), "former_names")  # Natural Earth: IN-OR
    assert "Ont." in _names(_row("admin1", "iso:CA-ON"), "abbreviations")
    assert {"UK", "Britain"} <= _names(_row("countries", "iso:GB"), "abbreviations") | _names(
        _row("countries", "iso:GB"), "aliases"
    )
    assert "Zaire" in _names(_row("countries", "iso:CD"), "former_names")


@pytest.mark.parametrize(
    ("airport", "city"),
    [
        ("ourairports:CYYZ", "geonames:6167865"),  # YYZ -> Toronto, not Mississauga
        ("ourairports:VIDP", "geonames:1273294"),  # DEL -> Delhi
        ("ourairports:VOBL", "geonames:1277333"),  # BLR -> Bengaluru
        ("ourairports:KEWR", "geonames:5128581"),  # EWR -> New York City
        ("ourairports:RJAA", "geonames:1850147"),  # NRT -> Tokyo
        ("ourairports:KOAK", "geonames:5378538"),  # OAK -> Oakland
    ],
)
def test_airports_serve_the_city_people_mean(airport, city):
    assert _row("airports", airport)["served_city"] == city
