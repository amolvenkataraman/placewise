"""Fame, duplicates, quotas and aliases of the notable places (packbuild.sources.notable)."""

import numpy as np
import pytest

from packbuild.sources.notable import aliases, rank


def test_percentile_is_the_share_at_or_below():
    assert rank.percentile([3.0, 1.0, 2.0, 2.0]).tolist() == [1.0, 0.25, 0.75, 0.75]
    assert rank.percentile([]).tolist() == []


def test_raw_fame_is_logarithmic():
    assert rank.raw_fame([0, 9, 99], [0, 9, 0]).tolist() == pytest.approx([0.0, 2.0, 2.0])


def test_fame_is_per_kind_and_lifts_a_country_s_best():
    # 40 stations in XA read far more than the 20 in XB; museums are ranked on their own
    raw = list(range(100, 140)) + list(range(20)) + [5.0, 1.0]
    kinds = ["station"] * 60 + ["museum"] * 2
    countries = ["XA"] * 40 + ["XB"] * 20 + ["XA", "XA"]
    fame = rank.fame(raw, kinds, countries)
    assert fame[39] == 1.0  # the best station anywhere
    best_xb = fame[59]  # last of the world's stations by reads, first in its country
    assert best_xb == pytest.approx((20 / 60 + 1.0) / 2)
    assert fame[60] == 1.0 and fame[61] == 0.5  # museums: the share of museums, no country group (< 20)


def test_popular_has_a_lower_floor_in_the_focus_countries():
    keep = rank.popular([1500, 500, 500, 100], ["XA", "XA", "IN", "CA"], min_views=1000, min_views_focus=200)
    assert keep.tolist() == [True, False, True, False]


def test_duplicates_keep_the_most_famous_within_reach():
    names = ["Union Station", "Union station", "The Union Station", "Union Station", "Other"]
    lat = [0.0, 0.001, 0.002, 1.0, 0.0]
    lon = [0.0, 0.0, 0.0, 0.0, 0.0]
    fame = [0.5, 0.9, 0.1, 0.4, 0.3]
    # 1 is the most famous; 0 is 111 m from it, 2 is 111 m from it; 3 is 111 km away
    assert rank.duplicates(names, lat, lon, fame) == {0: 1, 2: 1}


def test_cells_are_about_the_same_size_everywhere():
    # a 160 km line of points crosses about ten 16 km cells, on the equator and at 70°N alike
    for lat, span in ((0.0, 1.44), (70.0, 4.2)):
        found = len(set(rank.cells(np.full(400, lat), np.linspace(10, 10 + span, 400), cell_km=16).tolist()))
        assert found in (10, 11), (lat, found)
    assert len(set(rank.cells([45.0, 45.0001], [10.0, 10.0001]).tolist())) == 1


def test_quota_keeps_the_most_famous_per_cell_and_kind():
    n = 6
    lat, lon = [0.01] * n, [0.01] * n
    kinds = ["museum"] * 4 + ["university", "museum"]
    countries = ["XA", "XA", "XA", "IN", "XA", "XA"]
    fame = [0.9, 0.8, 0.7, 0.1, 0.05, 0.99]
    keep = rank.quota_keep(lat, lon, kinds, countries, fame, quota=1, quota_focus=2, floor=0.95)
    # 5 is above the floor and costs no slot; 0 takes the cell's one museum slot; 3, in a focus
    # country, may be the second; the university is exempt
    assert keep.tolist() == [True, False, False, True, True, True]


def test_aliases_are_cleaned_capped_and_short_forms_first():
    found = aliases.clean(
        "University of Waterloo",
        ["UW", "uwaterloo", "UWaterloo", "uwaterloo.ca", "the University of Waterloo", "Waterloo U",
         "Some Prize Named After It", "x" * 60, "YKF"],
        codes=["YKF"],
    )  # fmt: skip
    assert found == ["UW", "UWaterloo", "Waterloo U", "Some Prize Named After It"]
    assert len(aliases.clean("A", [f"Alias {i}" for i in range(20)])) == aliases.MAX_ALIASES


def test_spelling_variants_of_the_name_come_last():
    # Wikidata's aliases of Harmandir Sahib (QLever lists them alphabetically): the name people
    # use in English, Golden Temple, stays; spellings a typo-tolerant search finds anyway go last
    found = aliases.clean(
        "Harmandir Sahib",
        ["Darbar Sahib", "Darbār Sahib", "Golden Temple", "Harimandar", "Harimandir", "Harmandar",
         "Harmandar Sahib", "Harmandir", "Sri Harmandir Sahib", "Sri Harmandir Sahib Amritsar",
         "The Golden Temple", "The Golden Temple Amritsar"],
    )  # fmt: skip
    assert found == ["Darbar Sahib", "Harmandir", "Sri Harmandir Sahib", "Sri Harmandir Sahib Amritsar",
                     "Golden Temple", "The Golden Temple Amritsar"]  # fmt: skip
    # with room to spare, the variants are kept, after the rest
    assert aliases.clean("Harmandir Sahib", ["Harmandar", "Golden Temple"]) == ["Golden Temple", "Harmandar"]
    assert aliases.variant("Harmandir Sahib", "Harmandar Sahib")
    assert aliases.variant("Harmandir Sahib", "Harimandir")
    assert not aliases.variant("Harmandir Sahib", "Harmandir")  # a part of the name, spelled so
    assert not aliases.variant("Harmandir Sahib", "Darbar Sahib")
    assert not aliases.variant("Taj Mahal", "Taj")


def test_stations_get_a_short_name():
    assert aliases.clean("Mumbai Central railway station", [], kind="station") == ["Mumbai Central station"]
    assert aliases.clean("Union Station", ["Toronto Union Station"], kind="station") == [
        "Toronto Union Station"
    ]


def test_a_subway_station_beside_the_railway_station_is_a_duplicate():
    assert rank.duplicate_key("Union") == rank.duplicate_key("Union Station") == "union"
    assert rank.duplicate_key("The Mumbai Central railway station") == "mumbai central"
    assert rank.duplicate_key("Station") == "station"
    names, lat, lon = ["Union Station", "Union"], [0.0, 0.0004], [0.0, 0.0]
    assert rank.duplicates(names, lat, lon, [0.9, 0.5]) == {1: 0}
