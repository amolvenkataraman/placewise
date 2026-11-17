"""packbuild.clip: Greiner-Hormann intersection and difference, checked against the even-odd answer
on a grid of points (the same test the pack uses to look points up)."""

import numpy as np
import pytest

from packbuild import clip


def square(x0, y0, x1, y1):
    return np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], dtype=float)


def area(ring):
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)))


# an L, a comb (non-convex) and a star (self-similar spikes)
L_SHAPE = np.array([(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)], dtype=float)
COMB = np.array(
    [(0, 0), (5, 0), (5, 3), (4, 3), (4, 1), (3, 1), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3)], float
)
STAR = np.array(
    [(np.cos(a) * r, np.sin(a) * r) for k, a in enumerate(np.linspace(0, 2 * np.pi, 16, endpoint=False))
     for r in [3.0 if k % 2 == 0 else 1.2]]
)  # fmt: skip


def grid(lo=-4.13, hi=6.17, n=180):
    g = np.linspace(lo, hi, n)
    x, y = np.meshgrid(g, g)
    return x.ravel(), y.ravel()


def covered(polygons, x, y):
    """Even-odd over every ring of every polygon: how the pack answers."""
    out = np.zeros(x.shape, dtype=bool)
    for polygon in polygons:
        for ring in polygon:
            out ^= clip.inside(ring, x, y)
    return out


CASES = [
    (square(0, 0, 4, 4), square(2, 2, 6, 6)),  # corner overlap
    (square(0, 0, 4, 4), square(1, -1, 2, 5)),  # a bar through: two pieces
    (L_SHAPE, square(0.5, 0.5, 3, 3)),
    (COMB, square(-1, 2, 6, 2.5)),  # cuts every tooth off at the tip
    (STAR, square(-1, -1, 1.5, 4)),
    (STAR, square(-0.5, -0.5, 0.5, 0.5)),  # wholly inside: a hole
    (square(1, 1, 2, 2), square(0, 0, 4, 4)),  # wholly covered
    (square(0, 0, 1, 1), square(3, 3, 4, 4)),  # apart
]


@pytest.mark.parametrize(("subject", "cutter"), CASES)
def test_difference_matches_even_odd(subject, cutter):
    x, y = grid()
    want = clip.inside(subject, x, y) & ~clip.inside(cutter, x, y)
    got = covered(clip.difference(subject, cutter), x, y)
    assert np.array_equal(got, want)


@pytest.mark.parametrize(("subject", "cutter"), CASES)
def test_intersection_matches_even_odd(subject, cutter):
    x, y = grid()
    want = clip.inside(subject, x, y) & clip.inside(cutter, x, y)
    got = covered([[r] for r in clip.intersection(subject, cutter)], x, y)
    assert np.array_equal(got, want)


def test_pieces_holes_and_areas():
    pieces = clip.difference(square(0, 0, 4, 4), square(1, -1, 2, 5))
    assert sorted(area(p[0]) for p in pieces) == [4.0, 8.0]
    holed = clip.difference(square(0, 0, 4, 4), square(1, 1, 2, 2))
    assert len(holed) == 1 and len(holed[0]) == 2 and area(holed[0][0]) - area(holed[0][1]) == 15.0
    assert clip.difference(square(1, 1, 2, 2), square(0, 0, 4, 4)) == []
    assert clip.intersection(square(0, 0, 1, 1), square(3, 3, 4, 4)) == []


def test_winding_and_closing_vertex_do_not_matter():
    s = square(0, 0, 4, 4)
    closed_cw = np.vstack([s[::-1], s[-1:]])
    x, y = grid()
    a = covered(clip.difference(s, square(2, 2, 6, 6)), x, y)
    b = covered(clip.difference(closed_cw, square(2, 2, 6, 6)[::-1]), x, y)
    assert np.array_equal(a, b)


def test_touching_rings_are_nudged_apart():
    # shared edge and shared corners: degenerate for the method, solved by nudging the clip
    pieces = clip.difference(square(0, 0, 4, 4), square(2, 0, 4, 4))
    assert len(pieces) == 1 and area(pieces[0][0]) == pytest.approx(8.0, abs=1e-6)


def test_many_vertices():
    t = np.linspace(0, 2 * np.pi, 20_000, endpoint=False)
    wobbly = np.column_stack([(2 + 0.1 * np.sin(40 * t)) * np.cos(t), (2 + 0.1 * np.sin(40 * t)) * np.sin(t)])
    x, y = grid(-3, 3, 120)
    cutter = square(0.3, -3, 3, 3)
    want = clip.inside(wobbly, x, y) & ~clip.inside(cutter, x, y)
    assert np.array_equal(covered(clip.difference(wobbly, cutter), x, y), want)


def test_a_shared_edge_leaves_no_sliver():
    # the cutter covers the subject exactly along two edges: nothing of the subject is left
    assert clip.difference(square(0, 0, 2, 2), square(0, 0, 2.5, 2)) == []
    assert clip.difference(square(0, 0, 2, 2), square(-1, -1, 2, 2)) == []
