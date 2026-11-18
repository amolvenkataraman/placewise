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


def test_best_first_breaks_ties():
    assert best_first([1.0, 2.0, 1.0], [0.1, 0.0, 0.5]).tolist() == [1, 2, 0]
