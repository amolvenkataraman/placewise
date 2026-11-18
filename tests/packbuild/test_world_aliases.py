"""packbuild.world_aliases: curated and GeoNames alternate names -> alias columns on world layers."""

import zipfile

import pytest

from packbuild import aliases, world_aliases
from placewise.packs import LayerData


def test_columns_split_by_kind_dedupe_and_cap():
    rows = [
        (
            ("New York City", "New York City"),
            [
                ("New York City", "name"),  # its own name: dropped
                ("NYC", "short"),
                ("New York", "name"),
                ("Big Apple", "colloquial"),
                ("JFK", "code"),
                ("New Amsterdam", "former"),
                ("N.Y.", "abbr"),
                ("nyc", "code"),  # the same key twice: the first wins
                ("Gotham", "suppressed"),
            ],
            {"gotham"},
        ),
        (("Nowhere",), [], set()),
    ]
    cols = world_aliases.columns(rows, cap=6)
    assert cols == {
        "aliases": ["New York|Big Apple", ""],
        "abbreviations": ["NYC|N.Y.", ""],
        "former_names": ["New Amsterdam", ""],
        "airport_codes": ["JFK", ""],
    }
    assert world_aliases.columns(rows[:1], cap=2)["aliases"] == ["New York"]  # NYC, New York


def test_short_forms_in_capitals_are_abbreviations_others_aliases():
    cols = world_aliases.columns([(("X",), [("Vegas", "short"), ("LV", "short"), ("Ont.", "abbr")], set())])
    assert (cols["aliases"], cols["abbreviations"]) == (["Vegas"], ["LV|Ont."])


ALTERNATES = [
    ("1", "6167865", "iata", "YYZ"),
    ("2", "6167865", "en", "Old York", "", "", "", "1"),  # historic, not curated
    ("3", "1273874", "en", "Ernakulam"),  # suppressed by the curated dataset
    ("4", "1273874", "", "Cochin", "", "", "", "1"),  # historic and curated
    ("5", "6167865", "en", "Ottawa"),  # another city's name: not an alias of this one
    ("6", "6093943", "abbr", "Ont."),
    ("7", "6093943", "iata", "XXO"),  # codes only for cities
    ("8", "1261029", "", "Orissa", "1", "1", "", "1"),  # a state's former name (India names dataset)
    ("9", "6251999", "en", "Dominion of Canada"),
]


@pytest.fixture
def alternates(tmp_path):
    path = tmp_path / "alternateNamesV2.zip"
    lines = ["\t".join((list(r) + [""] * 10)[:10]) + "\n" for r in ALTERNATES]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("alternateNamesV2.txt", "".join(lines))
    return path


def _points(name, rows, columns):
    cols = {c: [r[i] for r in rows] for i, c in enumerate(columns)}
    return LayerData(name, "point", cols, ("geonames",), lat=[0.0] * len(rows), lon=[0.0] * len(rows))


@pytest.fixture
def layers():
    cities = _points(
        "cities",
        [
            ("geonames:6167865", "Toronto", "Toronto", "CA", 2_794_356),
            ("geonames:6094817", "Ottawa", "Ottawa", "CA", 1_017_449),
            ("geonames:1273874", "Kochi", "Kochi", "IN", 633_553),
        ],
        ("id", "name", "asciiname", "country", "population"),
    )
    admin1 = _points(
        "admin1",
        [
            ("iso:CA-ON", "Ontario", "CA", "geonames:6093943"),
            ("iso:IN-OD", "Odisha", "IN", "geonames:1261029"),
        ],
        ("id", "name", "country", "geonames"),
    )
    countries = _points(
        "countries", [("iso:CA", "Canada", "CA"), ("iso:CD", "Congo", "CD")], ("id", "name", "iso2")
    )
    return cities, admin1, countries


CURATED = aliases.for_packs(
    [
        {"text": "TOR", "kind": "short", "city": "Toronto", "country": "CA", "geonames": 6167865},
        {"text": "Cochin", "kind": "former", "city": "Kochi", "country": "IN", "geonames": 1273874},
        {"text": "Ernakulam", "kind": "suppress", "city": "Kochi", "country": "IN", "geonames": 1273874},
        {"text": "Zaire", "kind": "former", "country": "CD"},
    ]
)
INDIA = {
    "units": [
        {"lgd": "state:21", "name": "Odisha", "former": [{"name": "Orissa", "until": "2011"}]},
        {"lgd": "district:1", "name": "Kochi", "former": [{"name": "Old Kochi District", "until": "1"}]},
    ],
    "cities": [{"lgd": ["276600"], "name": "Kochi", "former": [{"name": "Cochin", "until": "1996"}]}],
}


def test_add_puts_alias_columns_on_the_three_layers(layers, alternates):
    cities, admin1, countries = layers
    counts = world_aliases.add(
        cities, admin1, countries, alternates, {"CA": 6251999, "CD": 203312}, CURATED, INDIA
    )
    assert list(cities.columns["abbreviations"]) == ["TOR", "", ""]
    assert list(cities.columns["airport_codes"]) == ["YYZ", "", ""]
    assert list(cities.columns["former_names"]) == ["", "", "Cochin"]
    assert list(cities.columns["aliases"]) == ["", "", ""]  # no Old York, Ernakulam or Ottawa
    assert list(admin1.columns["abbreviations"]) == ["Ont.", ""]
    assert list(admin1.columns["airport_codes"]) == ["", ""]
    assert list(admin1.columns["former_names"]) == ["", "Orissa"]
    assert list(countries.columns["aliases"]) == ["Dominion of Canada", ""]
    assert list(countries.columns["former_names"]) == ["", "Zaire"]
    for layer in layers:
        assert all(layer.types[c] == "str" for c in world_aliases.COLUMNS)
        assert "placewise-names" in layer.sources
    assert counts["cities"] == 2 and counts["admin1"] == 2 and counts["countries"] == 2
