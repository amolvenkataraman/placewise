"""Merging one place found in several packs, and keeping different places apart."""

from placewise.search.dedupe import merge, preference

BOX = {  # candidate -> (south, west, north, east) of its synthetic outline
    1: (0.0, 0.0, 1.0, 1.0),
    2: (-1.0, -1.0, 2.0, 2.0),
}


def contains(i, lat, lon):
    s, w, n, e = BOX[i]
    return s <= lat <= n and w <= lon <= e


def item(keys, kind, lat, lon, polygon=False, detailed=False):
    return (frozenset(keys), kind, lat, lon, polygon, detailed)


def test_city_point_city_outline_and_metro_outline_merge_under_the_city_outline():
    items = [
        item({"alpha"}, "locality", 0.5, 0.5),  # the world pack's point
        item({"alpha"}, "locality", 0.4, 0.4, polygon=True, detailed=True),  # municipality outline
        item({"alpha"}, "region", 0.3, 0.3, polygon=True, detailed=True),  # metro area outline
    ]
    assert merge([0, 1, 2], items, contains) == [[1, 0, 2]]


def test_state_and_city_of_one_name_stay_apart():
    items = [item({"alpha"}, "admin1", 0.5, 0.5, polygon=True), item({"alpha"}, "locality", 0.5, 0.5)]
    groups = merge([0, 1], items, lambda i, lat, lon: True)
    assert groups == [[0], [1]]


def test_same_name_far_apart_stays_apart():
    items = [item({"beta"}, "locality", 0.0, 0.0), item({"beta"}, "locality", 10.0, 10.0)]
    assert merge([0, 1], items, contains) == [[0], [1]]


def test_points_close_together_merge():
    items = [item({"beta"}, "park", 0.0, 0.0), item({"beta"}, "park", 0.05, 0.05)]
    assert merge([0, 1], items, contains) == [[0, 1]]


def test_different_names_never_merge():
    items = [item({"alpha"}, "locality", 0.5, 0.5), item({"gamma"}, "locality", 0.5, 0.5)]
    assert merge([0, 1], items, contains) == [[0], [1]]


def test_outline_without_the_point_inside_stays_apart():
    items = [
        item({"alpha"}, "park", 0.5, 0.5, polygon=True),
        item({"alpha"}, "park", 5.0, 5.0),
    ]
    assert merge([0, 1], items, lambda i, lat, lon: contains(1, lat, lon)) == [[0], [1]]


def test_groups_keep_score_order():
    items = [item({"a"}, "locality", 0, 0), item({"b"}, "locality", 0, 0), item({"a"}, "locality", 0, 0.01)]
    assert merge([1, 0, 2], items, contains) == [[1], [0, 2]]


def test_preference():
    assert preference("locality", False, False) > preference("region", True, True)
    assert preference("park", True, False) > preference("park", False, False)
    assert preference("admin1", True, True) > preference("admin1", True, False)
