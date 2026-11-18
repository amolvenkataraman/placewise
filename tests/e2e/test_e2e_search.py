"""Forward search on the real packs: public places only. Skipped when the packs have no name index
(build them with the name index: `uv run python -m packbuild.<builder>`).

Disputed areas: nothing is asserted about sovereignty except under worldview IN."""

import time
from functools import cache

import pytest
from e2e_kit import pack_path

from placewise.model import PlaceKind

PACKS = (
    "world",
    "usa",
    "can",
    "ind",
    "world-water",
    "usa-parks",
    "can-parks",
    "world-parks",
    "world-notable",
)


@cache
def _geocoder():
    from placewise.engine import Geocoder
    from placewise.packs import open_pack

    paths = [p for p in (pack_path(n) for n in PACKS) if p is not None]
    packs = [open_pack(p) for p in paths]
    if not packs or packs[0].name != "world" or packs[0].names is None:
        return None
    return Geocoder(packs=packs)


@pytest.fixture(scope="module")
def geo():
    g = _geocoder()
    if g is None:
        pytest.skip("no world pack with a name index (rebuild the packs with names/)")
    return g


def has(geo, *packs):
    names = {p.name for p in geo.packs if p.names is not None}
    missing = [p for p in packs if p not in names]
    if missing:
        pytest.skip(f"packs without a name index: {', '.join(missing)}")


def top(geo, text, **options):
    found = geo.find(text, **options)
    assert found, f"nothing found for {text!r}"
    return found[0]


# (query, packs, expected name, region, country, kind); None: not checked
PLACES = [
    ("Toronto", ("can",), "Toronto", "Ontario", "CA", PlaceKind.LOCALITY),
    ("Springfield, IL", ("usa",), "Springfield", "Illinois", "US", PlaceKind.LOCALITY),
    ("Paris, France", (), "Paris", None, "FR", PlaceKind.LOCALITY),
    ("Paris, TX", ("usa",), "Paris", "Texas", "US", PlaceKind.LOCALITY),
    ("Bengaluru", (), "Bengaluru", "Karnataka", "IN", None),
    ("Bangalore", (), "Bengaluru", "Karnataka", "IN", None),
    ("Gurgaon", (), "Gurugram", "Haryana", "IN", None),
    ("Bombay", (), "Mumbai", "Maharashtra", "IN", None),
    ("Mississauga", ("can",), "Mississauga", "Ontario", "CA", PlaceKind.LOCALITY),
    ("Las Vegas", ("usa",), "Las Vegas", "Nevada", "US", PlaceKind.LOCALITY),
    ("Brooklyn", (), "Brooklyn", "New York", "US", None),
    ("Ontario", (), "Ontario", None, "CA", PlaceKind.ADMIN1),
    ("Karnataka", (), "Karnataka", None, "IN", PlaceKind.ADMIN1),
    ("Clark County", ("usa",), "Clark County", "Nevada", "US", PlaceKind.ADMIN2),  # by population
    ("Peel Region", ("can",), "Peel", "Ontario", "CA", None),
    ("Yosemite", ("usa-parks",), "Yosemite National Park", "California", "US", PlaceKind.PARK),
    ("Yosemite National Park", ("usa-parks",), "Yosemite National Park", "California", "US", PlaceKind.PARK),
    ("Lake Tahoe", ("world-water",), "Lake Tahoe", None, None, PlaceKind.WATER),
    ("Lake Ontario", ("world-water",), "Lake Ontario", None, None, PlaceKind.WATER),
    ("Arabian Sea", ("world-water",), "Arabian Sea", None, None, PlaceKind.WATER),
    ("Ganges", ("world-water",), "Ganges", None, None, PlaceKind.WATER),
    (
        "Rouge National Urban Park",
        ("can-parks",),
        "Rouge National Urban Park",
        "Ontario",
        "CA",
        PlaceKind.PARK,
    ),
    # typos and partials
    ("Torono", ("can",), "Toronto", "Ontario", "CA", PlaceKind.LOCALITY),
    ("Missisauga", ("can",), "Mississauga", "Ontario", "CA", PlaceKind.LOCALITY),
    ("Yosemit", ("usa-parks",), "Yosemite National Park", "California", "US", PlaceKind.PARK),
]


@pytest.mark.parametrize(("text", "packs", "name", "region", "country", "kind"), PLACES)
def test_places(geo, text, packs, name, region, country, kind):
    has(geo, "world", *packs)
    usa = next((p for p in geo.packs if p.name == "usa"), None)
    if text == "Clark County" and usa is not None and "population" not in usa["counties"].fields:
        pytest.skip("usa counties without population (packs built before it): every Clark County ranks alike")
    e = top(geo, text)
    assert e.place.name == name, (text, e.place.name, e.place.id)
    if region is not None:
        assert e.region == region, (text, e.region)
    if country is not None:
        assert e.country == country
    if kind is not None:
        assert e.place.kind == kind
    assert e.bbox.contains(e.point.lat, e.point.lon)


def test_scarborough_and_banff_find_their_places(geo):
    assert top(geo, "Scarborough").place.name == "Scarborough"
    has(geo, "can-parks")
    assert top(geo, "Banff").country == "CA"


@pytest.mark.parametrize(
    ("text", "packs", "region_id"),
    [
        ("Bay Area", ("usa",), "region:sf-bay-area"),
        ("GTA", ("can",), "region:gta"),
        ("Delhi NCR", ("ind",), "region:delhi-ncr"),
        ("Golden Horseshoe", ("can",), "region:golden-horseshoe"),
        ("bengaluru urban", ("ind",), None),
    ],
)
def test_regions(geo, text, packs, region_id):
    has(geo, "world", *packs)
    found = geo.find(text, limit=3)
    if region_id is None:
        assert "Bengaluru" in found[0].place.name
    else:
        assert region_id in [e.place.id for e in found[:2]], [e.place.id for e in found]


@pytest.mark.parametrize(
    ("code", "packs", "kind", "name"),
    [
        ("M5V", ("can",), PlaceKind.POSTAL_CODE, "M5V"),
        ("94105", ("usa",), PlaceKind.POSTAL_CODE, "94105"),
        ("560001", ("ind",), PlaceKind.POSTAL_CODE, None),
        ("CA-ON", (), PlaceKind.ADMIN1, "Ontario"),
        ("US", (), PlaceKind.COUNTRY, "United States of America"),
        ("IND", (), PlaceKind.COUNTRY, "India"),
        ("census:0646870", ("usa",), PlaceKind.LOCALITY, "Menlo Park"),
        ("iso:IN-KA", (), PlaceKind.ADMIN1, "Karnataka"),
    ],
)
def test_codes_and_ids(geo, code, packs, kind, name):
    has(geo, "world", *packs)
    e = top(geo, code)
    assert e.place.kind == kind, (code, e.place)
    if name is not None:
        assert e.place.name == name


@pytest.mark.parametrize(
    ("code", "city", "country"),
    [
        ("YYZ", "Toronto", "CA"),
        ("CYYZ", "Toronto", "CA"),
        ("DEL", "Delhi", "IN"),
        ("BLR", "Bengaluru", "IN"),
        ("SFO", "San Francisco", "US"),
        ("JFK", "New York", "US"),
    ],
)
def test_airport_codes_mean_the_city_they_serve(geo, code, city, country):
    found = geo.find(code, limit=3)
    assert found[0].place.name.startswith(city) and found[0].country == country, [e.place.id for e in found]
    assert found[1].place.kind == PlaceKind.AIRPORT


def test_airport_code_with_kinds_or_the_word_is_the_airport(geo):
    assert top(geo, "YYZ", kinds="airport").place.name.startswith("Toronto Pearson")
    assert top(geo, "YYZ airport").place.codes["iata"] == "YYZ"


def test_prefix_while_typing(geo):
    has(geo, "can")
    # Mississippi (the state) is as likely without context; Mississauga is among the first few, and
    # first for someone near Toronto
    assert "Mississauga" in [e.place.name for e in geo.find("Mississ", prefix=True, limit=3)]
    assert geo.find("Mississ", prefix=True, near=(43.65, -79.38))[0].place.name == "Mississauga"


def test_coordinates_as_text(geo):
    e = top(geo, "43.6426, -79.3871")
    assert e.city == "Toronto" and e.country == "CA" and e.place.id.startswith("geo:")


# -- context outside the text (owner requirement) ---------------------------------------------------


def test_paris_with_country_usa_is_paris_texas(geo):
    has(geo, "usa")
    e = top(geo, "Paris", country="USA")
    assert (e.place.name, e.region, e.country) == ("Paris", "Texas", "US")
    for spelling in ("US", "United States", "U.S."):
        assert top(geo, "Paris", country=spelling).region == "Texas"


def test_paris_alone_is_paris_france(geo):
    e = top(geo, "Paris")
    assert (e.place.name, e.country) == ("Paris", "FR")


def test_springfield_with_state(geo):
    has(geo, "usa")
    assert top(geo, "Springfield", state="IL").region == "Illinois"
    assert top(geo, "Springfield", admin1="Missouri").region == "Missouri"


def test_richmond_in_canada_is_richmond_bc(geo):
    has(geo, "can")
    e = top(geo, "Richmond", country="CA")
    assert (e.place.name, e.region) == ("Richmond", "British Columbia")


def test_victoria_near_victoria_bc(geo):
    e = top(geo, "Victoria", near=(48.43, -123.37))
    assert e.region == "British Columbia" and e.country == "CA"


def test_lakes_within_the_bay_area(geo):
    has(geo, "usa", "world-water")
    found = geo.find("Lake", within="region:sf-bay-area", kinds="water")
    assert found and all(e.place.kind == PlaceKind.WATER for e in found)
    assert all(36.8 < e.point.lat < 38.9 and -123.7 < e.point.lon < -121.2 for e in found)


def test_text_context_and_arguments_combine_arguments_win(geo):
    has(geo, "usa")
    assert top(geo, "Paris, TX", country="FR").country == "FR"


def test_worldview_india_reports_india_for_indian_claims(geo):
    e = top(geo, "Gilgit", worldview="IN")
    assert e.country == "IN"


# places whose point lies just off the world pack's 1:10m coast (harbours, islands, river banks):
# (query, packs, expected name, region, country)
COASTAL = [
    ("Boston", ("usa",), "Boston", "Massachusetts", "US"),
    ("Key West", ("usa",), "Key West", "Florida", "US"),
    ("Corpus Christi", ("usa",), "Corpus Christi", "Texas", "US"),
    ("Biloxi", ("usa",), "Biloxi", "Mississippi", "US"),
    ("Quebec City", (), "Québec", "Québec", "CA"),
    ("Tofino", ("can",), "Tofino", "British Columbia", "CA"),
    ("Kochi", ("ind",), "Kochi", "Kerala", "IN"),
    ("Alappuzha", ("ind",), "Alappuzha", "Kerala", "IN"),
    ("Victoria, Hong Kong", (), "Victoria", "Central and Western", "HK"),
    ("Dubrovnik", (), "Dubrovnik", None, "HR"),
    ("Lagos", (), "Lagos", "Lagos", "NG"),
    ("Mombasa", (), "Mombasa", None, "KE"),
    ("Darwin", (), "Darwin", "Northern Territory", "AU"),
    ("Suva", (), "Suva", None, "FJ"),
    ("Guayaquil", (), "Guayaquil", "Guayas", "EC"),
]


@pytest.mark.parametrize(("text", "packs", "name", "region", "country"), COASTAL, ids=[c[0] for c in COASTAL])
def test_coastal_places_are_in_the_country_and_region_of_their_coast(geo, text, packs, name, region, country):
    has(geo, "world", *packs)
    e = top(geo, text)
    assert e.place.name == name, (text, e.place.id)
    assert e.country == country and e.region is not None, (text, e.country, e.region)
    if region is not None:
        assert e.region == region, (text, e.region)
    full = geo.lookup(e.point.lat, e.point.lon)  # what reverse lookup says of the same point
    assert (e.country, e.region) == (full.cc, full.admin1.name)
    assert e.place.codes["iso2"] == country


def test_coastal_places_pass_country_and_state_filters(geo):
    has(geo, "usa", "ind")
    assert top(geo, "Boston", country="US", admin1="MA").place.name == "Boston"
    assert top(geo, "Boston, MA").region == "Massachusetts"
    assert top(geo, "Kochi", country="IN").region == "Kerala"
    assert top(geo, "Kochi, Kerala").place.name == "Kochi"
    assert top(geo, "Kochi", worldview="IN").country == "IN"


# -- notable places (once world-notable exists) -----------------------------------------------------


@pytest.mark.parametrize(
    ("name", "qid"),
    [
        ("CN Tower", "Q134883"),
        ("Eiffel Tower", "Q243"),
        ("Golden Gate Bridge", "Q44440"),
        ("University of Waterloo", "Q1049470"),
        ("IIT Bombay", "Q1661242"),  # an alias of "Indian Institute of Technology Bombay"
        ("Union Station Toronto", "Q511316"),
        ("Taj Mahal", "Q9141"),
        ("Gateway of India", "Q864862"),
        ("Shibuya Crossing", "Q21083961"),  # an alias of "Shibuya scramble crossing"
    ],
)
def test_notable(geo, name, qid):
    has(geo, "world-notable")
    e = top(geo, name)
    assert f"wikidata:{qid}" in {e.place.id, *(p.id for p in e.alternates)}


# -- speed ------------------------------------------------------------------------------------------

QUERIES = [(p.values if hasattr(p, "values") else p)[0] for p in PLACES] + [
    "Bay Area",
    "GTA",
    "YYZ",
    "M5V",
    "94105",
    "560001",
    "US",
    "Mississ",
]


def test_latency_report(geo, capsys):
    """Warm latency per query (target < 10 ms): each query once uncached, then repeated."""
    first, again = {}, {}
    for q in QUERIES:
        t = time.perf_counter()
        geo.find(q)
        first[q] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        for _ in range(5):
            geo.find(q)
        again[q] = (time.perf_counter() - t) * 200
    with capsys.disabled():
        print("\nquery: first ms / repeat ms")
        for q in QUERIES:
            print(f"  {q!r}: {first[q]:.1f} / {again[q]:.1f}")
        med = sorted(again.values())[len(again) // 2]
        print(f"median repeat {med:.1f} ms, max first {max(first.values()):.1f} ms")


# -- location search with packs ---------------------------------------------------------------------


def test_location_search_gets_places_from_search(geo):
    from placewise.search import SearchGazetteer
    from placewise.text import parse_location

    has(geo, "can", "usa")
    gaz = SearchGazetteer(geo)
    parsed = parse_location("Hybrid - Mississauga, ON; US-CA-Menlo Park", gaz)
    mississauga, menlo = parsed.parts
    assert mississauga.city_verified and mississauga.place.codes["admin1"] == "ON"
    assert 43.5 < mississauga.place.point.lat < 43.7
    assert menlo.place.id == "census:0646870" and menlo.place.bbox is not None
