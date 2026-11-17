"""Splitting polygons along a clip region (packbuild.ind.clip): synthetic squares, checked by area
and by even-odd membership of sample points."""

import numpy as np
import pytest

from packbuild.ind import clip
from packbuild.polygons import signed_area


def square(x0, y0, x1, y1):
    """Clockwise (x east, y north), open."""
    return np.array([(x0, y0), (x0, y1), (x1, y1), (x1, y0)], dtype=np.float64)


def area(rings):
    """Even-odd area: shells count positive, holes negative (clockwise shells)."""
    return -sum(signed_area(r) for r in rings)


GRID = np.stack(np.meshgrid(np.linspace(-0.95, 2.95, 40), np.linspace(-0.95, 2.95, 40)), -1).reshape(-1, 2)


def members(rings):
    return clip.inside(rings, GRID[:, 0], GRID[:, 1])


def check(subject, clip_rings, in_area, out_area, **kw):
    inner, outer = clip.split(subject, clip_rings, **kw)
    assert area(inner) == pytest.approx(in_area) and area(outer) == pytest.approx(out_area)
    s, c = members(subject), members(clip_rings)
    assert np.array_equal(members(inner), s & c) and np.array_equal(members(outer), s & ~c)
    return inner, outer


def test_half_inside():
    check([square(0, 0, 2, 2)], [square(1, -1, 3, 3)], 2.0, 2.0)


def test_corner_overlap_meets_exactly():
    inner, outer = check([square(0, 0, 2, 2)], [square(1.5, 1.5, 3, 3)], 0.25, 3.75)
    shared = {tuple(p) for r in inner for p in r} & {tuple(p) for r in outer for p in r}
    assert {(1.5, 2.0), (2.0, 1.5), (1.5, 1.5)} <= shared  # the cut points are the same floats


def test_clip_island_inside_the_subject_is_a_hole_of_the_outside_part():
    inner, outer = check([square(0, 0, 2, 2)], [square(0.5, 0.5, 1, 1)], 0.25, 3.75)
    assert len(inner) == 1 and len(outer) == 2


def test_disjoint_and_covered():
    check([square(0, 0, 1, 1)], [square(2, 2, 3, 3)], 0.0, 1.0)
    check([square(0.2, 0.2, 0.8, 0.8)], [square(0, 0, 1, 1)], 0.36, 0.0)
    check([square(0, 0, 1, 1)], [], 0.0, 1.0)


def test_neighbouring_clip_polygons_act_as_one_region():
    # two countries sharing a border across the subject: their shared edge cancels
    inner, _ = check([square(0, 0, 2, 2)], [square(1, -1, 2.5, 1), square(1, 1, 2.5, 3)], 2.0, 2.0)
    assert len(inner) == 1


def test_subject_with_a_hole():
    subject = [square(0, 0, 2, 2), square(0.5, 0.5, 1.5, 1.5)[::-1]]
    check(subject, [square(1, -1, 3, 3)], 1.5, 1.5)


def test_a_faster_membership_test_can_stand_in():
    region = [square(1, -1, 3, 3)]
    check([square(0, 0, 2, 2)], region, 2.0, 2.0, in_clip=lambda x, y: (x > 1) & (x < 3))


def test_inside_is_even_odd():
    rings = [square(0, 0, 2, 2), square(0.5, 0.5, 1.5, 1.5)]
    assert clip.inside(rings, [0.25, 1.0, 3.0], [0.25, 1.0, 1.0]).tolist() == [True, False, False]
