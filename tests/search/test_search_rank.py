"""The ranking terms: match quality, prior, context and distance."""

import numpy as np
import pytest

from placewise.constants import search as const
from placewise.constants.names import ALIAS, CODE, OFFICIAL
from placewise.search.rank import base_scores, best_first, context_factors, near_factors


def scores(match, rank, name_kind=OFFICIAL, fuzzy=False, factor=1.0):
    n = len(match)
    return base_scores(match, rank, [name_kind] * n, [fuzzy] * n, [factor] * n)


def test_exact_beats_prefix_and_prior_orders_equal_matches():
    s = scores([1.0, 0.6, 1.0], [0.5, 0.9, 0.2])
    assert s[0] > s[2] and s[0] > s[1]


def test_big_place_beats_small_one_of_the_same_name():
    big, small = scores([1.0, 1.0], [0.85, 0.3])
    assert big > 2 * small


def test_zero_prior_still_counts():
    assert scores([1.0], [0.0])[0] == pytest.approx(const.PRIOR_FLOOR)


def test_fuzzy_and_alias_matches_are_worth_a_little_less():
    exact = scores([1.0], [0.5])[0]
    assert scores([1.0], [0.5], fuzzy=True)[0] < exact
    assert scores([1.0], [0.5], name_kind=ALIAS)[0] < exact
    assert scores([1.0], [0.5], name_kind=CODE)[0] == exact


def test_context_first_reading_later_reading_and_outside():
    contexts = ([("US", "IL"), ("IL", None)],)
    country = np.array(["US", "IL", "US", None], dtype=object)
    admin1 = np.array(["IL", None, "MO", None], dtype=object)
    got = context_factors([0, 0, 0, 0], contexts, country, admin1)
    assert got.tolist() == [1.0, const.CONTEXT_LATER_READING, 0.0, 0.0]


def test_context_with_nothing_inside_keeps_everything_lightly():
    got = context_factors(
        [0, 0], ([("FR", None)],), np.array(["US", "CA"], dtype=object), np.array([None, None])
    )
    assert got.tolist() == [const.CONTEXT_MISS_FACTOR] * 2


def test_candidates_without_a_context_are_untouched():
    got = context_factors(
        [-1, 0], ([("FR", None)],), np.array(["US", "FR"], dtype=object), np.array([None, None])
    )
    assert got.tolist() == [1.0, 1.0]


def test_near_decays_from_the_extent_not_the_point():
    near = (42.37, -71.11)
    f = near_factors([42.37, 52.2], [-71.11, 0.12], [0.0, 0.0], near)
    assert f[0] == pytest.approx(1.0) and f[1] == pytest.approx(const.NEAR_FLOOR, abs=0.01)
    wide = near_factors([45.0], [-71.11], [400.0], near)[0]
    assert wide == pytest.approx(1.0)


def test_a_typo_of_an_alternate_name_is_worth_less_than_a_typo_of_the_name():
    typo = scores([5 / 6], [0.7], fuzzy=True)[0]
    alias_typo = scores([5 / 6], [0.7], name_kind=ALIAS, fuzzy=True)[0]
    worth = const.NAME_KIND_FACTOR["alias"] * const.FUZZY_ALIAS_FACTOR
    assert alias_typo == pytest.approx(typo * worth)
    # "Colaba": the Mumbai neighbourhood (prior 0.2) before Cuiaba, a big city (0.68) one letter
    # from its alternate spelling Culaba
    assert scores([1.0], [0.2])[0] > scores([5 / 6], [0.683], name_kind=ALIAS, fuzzy=True)[0]


def test_a_small_place_reaches_less_far_than_a_big_one():
    near = (12.97, 77.59)  # central Bengaluru
    # a town 80 km away and a neighbourhood 3 km away, both with no extent
    far_town, close_hood = near_factors([13.69, 12.94], [77.59, 77.62], [0.0, 0.0], near, [0.4, 0.2])
    big_far = near_factors([13.69], [77.59], [0.0], near, [const.NEAR_FULL_REACH_RANK])[0]
    unranked = near_factors([13.69], [77.59], [0.0], near)[0]
    assert big_far == pytest.approx(unranked)  # a big place reaches as far as before
    assert far_town < big_far - 0.25 and close_hood > 0.75
    # "Kora" typed near Bengaluru: Koramangala (prior 0.2, 3 km) before Koratagere (0.4, 80 km)
    hood, town = base_scores(
        [4 / 11, 4 / 10], [0.2, 0.4], [OFFICIAL] * 2, [False] * 2, [1.0] * 2, prefix=[True] * 2
    )
    assert hood * close_hood > town * far_town


def test_best_first_breaks_ties():
    assert best_first([1.0, 2.0, 1.0], [0.1, 0.0, 0.5]).tolist() == [1, 2, 0]


def test_prefix_matches_rank_by_prior_more_than_by_how_much_is_typed():
    # "Mississ": Mississauga (7 of 11 letters, a big city) beats Mississagi (7 of 10, a small park)
    n = 2
    city, park = base_scores(
        [7 / 11, 7 / 10], [0.7, 0.5], [OFFICIAL] * n, [False] * n, [1.0] * n, prefix=[True] * n
    )
    assert city > park
    exact = base_scores([1.0], [0.5], [OFFICIAL], [False], [1.0], prefix=[True])[0]
    assert exact == pytest.approx(scores([1.0], [0.5])[0])


def test_served_city_weighs_population_by_distance():
    from placewise.search.rank import served_city_scores

    # San Francisco (870k, 21 km) over San Jose (1M, 47 km);
    # Toronto (2.7M, 22 km) over Mississauga (720k, 5 km)
    sf, sj = served_city_scores([870_000, 1_000_000], [21.0, 47.0])
    assert sf > sj
    toronto, mississauga = served_city_scores([2_700_000, 720_000], [22.0, 5.0])
    assert toronto > mississauga


def _kinds(*names):
    from placewise.constants.names import PLACE_KINDS

    return np.array([PLACE_KINDS.index(n) for n in names])


def test_what_is_named_after_a_place_comes_after_it():
    from placewise.search.rank import named_after_factors

    # "Richmond": a city, a railway station and a university known as Richmond, a park whose alias
    # it is, a river officially called it, and a prefix match left out (key None)
    kind = _kinds("locality", "station", "university", "park", "water", "station")
    name_kind = np.array([OFFICIAL, OFFICIAL, ALIAS, ALIAS, OFFICIAL, OFFICIAL])
    rank = np.array([0.7, 0.8, 0.85, 0.8, 0.6, 0.9])
    keys = np.array(["richmond"] * 5 + [None], dtype=object)
    got = named_after_factors(kind, name_kind, rank, keys, typed_word=True)
    s = const.SHADOW_FACTOR
    assert got.tolist() == [1.0, s, s, s, 1.0, 1.0]


def test_only_a_place_of_some_size_puts_namesakes_after_it():
    from placewise.search.rank import named_after_factors

    # a hamlet called Times Square leaves the landmark alone; another name leaves it alone too
    kind = _kinds("locality", "landmark")
    keys = np.array(["times square", "times square"], dtype=object)
    small = named_after_factors(kind, np.array([OFFICIAL] * 2), np.array([0.2, 0.9]), keys, typed_word=True)
    assert small.tolist() == [1.0, 1.0]
    other = np.array(["times square", "madison square garden"], dtype=object)
    big = named_after_factors(kind, np.array([OFFICIAL] * 2), np.array([0.6, 0.9]), other, typed_word=True)
    assert big.tolist() == [1.0, 1.0]


def test_a_code_reads_as_the_place_when_typed_as_a_word_or_abbreviated():
    from placewise.constants.names import ABBREVIATION
    from placewise.search.rank import named_after_factors

    # "Goa": Goa (the state) over Genoa, whose airport's code is GOA; a city found by its airport
    # code doesn't count as a place named so; in capitals the code is meant as a code
    kind = _kinds("admin1", "locality", "airport")
    name_kind = np.array([OFFICIAL, CODE, CODE])
    rank = np.array([0.8, 0.85, 0.8])
    keys = np.array(["goa"] * 3, dtype=object)
    s = const.SHADOW_FACTOR
    assert named_after_factors(kind, name_kind, rank, keys, typed_word=True).tolist() == [1.0, s, s]
    assert named_after_factors(kind, name_kind, rank, keys, typed_word=False).tolist() == [1.0, 1.0, 1.0]
    # "SF" in capitals: San Francisco's abbreviation over a station's code; an airport code stays
    # the airport's ("DEL" is Delhi's airport even though Delaware is abbreviated Del.)
    kind = _kinds("locality", "station", "airport")
    abbr = np.array([ABBREVIATION, CODE, CODE])
    assert named_after_factors(kind, abbr, rank, keys, typed_word=False).tolist() == [1.0, s, 1.0]
    # "YYZ": Toronto by its airport code doesn't push the airport down
    toronto = named_after_factors(
        _kinds("locality", "airport"), np.array([CODE, CODE]), rank[:2], keys[:2], typed_word=False
    )
    assert toronto.tolist() == [1.0, 1.0]


def test_a_postal_code_means_the_postal_area():
    from placewise.search.rank import postal_codes_first

    # "10001": the ZIP Code before a famous Spanish railway station whose code is 10001
    kind = _kinds("postal_code", "station", "station")
    got = postal_codes_first(np.array([0.3, 0.8, 0.5]), kind, np.array([CODE, CODE, OFFICIAL]))
    assert got.tolist() == pytest.approx([0.3, 0.3 * const.CODE_AFTER_POSTAL, 0.5])
    alone = postal_codes_first(np.array([0.8, 0.5]), kind[1:], np.array([CODE, CODE]))
    assert alone.tolist() == [0.8, 0.5]


def test_while_typing_what_is_named_after_a_place_comes_after_it():
    from placewise.search.rank import named_after_factors

    # "San Fran": the city before the zoo, airport and bay named after it; a station called
    # "San Francisco Centre" for a different reason is still named after it
    kind = _kinds("locality", "park", "airport", "water", "park")
    name_kind = np.array([OFFICIAL] * 5)
    rank = np.array([0.7, 0.9, 0.9, 0.8, 0.9])
    keys = np.array(
        ["san francisco", "san francisco zoo", "san francisco international airport", "san francisco bay",
         "san franciscan hills"], dtype=object,
    )  # fmt: skip
    s = const.SHADOW_FACTOR
    assert named_after_factors(kind, name_kind, rank, keys, typed_word=True).tolist() == [1.0, s, s, s, 1.0]


def test_while_typing_places_come_before_famous_buildings():
    from placewise.search.rank import typing_factors

    # "Toro": Toron (a famous castle, 4 of 5 letters typed) after Toronto (4 of 7)
    kind = _kinds("locality", "building", "building")
    got = typing_factors(kind, np.array([True, True, False]))
    assert got.tolist() == [1.0, const.TYPING_FACILITY_FACTOR, 1.0]
