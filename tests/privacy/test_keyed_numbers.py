"""Keyed pseudo-random numbers: the batched form must give exactly what one call per row gives."""

import pytest

from placewise.privacy._common import keyed_uniforms, keyed_uniforms_each

KEY = bytes(range(32))


@pytest.mark.parametrize("n", [0, 1, 2, 4, 5, 9])
def test_each_row_matches_its_own_call(n):
    rows = [(0, 0), (-1, 7), (2**70, -(2**70)), (123456, 654321)]
    batched = keyed_uniforms_each(KEY, "noise", 0.01, rows=rows, n=n)
    assert batched == [keyed_uniforms(KEY, "noise", 0.01, r, c, n=n) for r, c in rows]


def test_rows_of_one_and_no_shared_parts():
    assert keyed_uniforms_each(KEY, "snap-row", rows=[(5,), (-3,)]) == [
        keyed_uniforms(KEY, "snap-row", 5),
        keyed_uniforms(KEY, "snap-row", -3),
    ]
    assert keyed_uniforms_each(KEY, "x", 1.0, rows=[]) == []


def test_values_are_pinned():
    # a change to the message layout would silently move every user's cuts and noise
    assert keyed_uniforms(KEY, "zone-extra", "home") == [0.8967617490146716]
    assert keyed_uniforms_each(KEY, "zone-extra", "home", rows=[()]) == [[0.8967617490146716]]
