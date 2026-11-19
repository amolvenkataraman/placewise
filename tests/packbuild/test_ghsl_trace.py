"""Cell-edge rings of grid-cell clusters (packbuild.sources.ghsl.trace)."""

import numpy as np

from packbuild.sources.ghsl.trace import rings, subtract


def runs_of(picture):
    """Runs (row, c0, c1) of the '#' cells of a list of strings."""
    out = []
    for r, line in enumerate(picture):
        c = 0
        while c < len(line):
            if line[c] == "#":
                e = c
                while e < len(line) and line[e] == "#":
                    e += 1
                out.append((r, c, e))
                c = e
            else:
                c += 1
    return out


def area(ring):
    """Signed area in a y-up frame (x = col, y = -row): negative = clockwise."""
    x, y = ring[:, 0].astype(float), -ring[:, 1].astype(float)
    return 0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def test_subtract():
    assert subtract([(0, 10)], [(2, 4), (6, 7)]) == [(0, 2), (4, 6), (7, 10)]
    assert subtract([(0, 3), (5, 9)], [(-1, 1), (8, 20)]) == [(1, 3), (5, 8)]
    assert subtract([(0, 3)], []) == [(0, 3)]
    assert subtract([(2, 3)], [(0, 5)]) == []


def test_one_cell_is_a_clockwise_square():
    (ring,) = rings([(4, 7, 8)])
    assert sorted(map(tuple, ring.tolist())) == [(7, 4), (7, 5), (8, 4), (8, 5)]
    assert area(ring) == -1


def test_l_shape_has_six_corners():
    (ring,) = rings(runs_of(["##.", "###"]))
    assert len(ring) == 6 and area(ring) == -5


def test_hole_runs_the_other_way():
    found = rings(runs_of(["###", "#.#", "###"]))
    assert sorted(area(r) for r in found) == [-9, 1]


def test_cells_touching_at_a_corner_stay_apart():
    # a ring of 8 cells around a hole whose corner pinches: the right turn keeps them separate
    found = rings(runs_of(["#.", ".#"]))
    assert sorted(area(r) for r in found) == [-1, -1]
    found = rings(runs_of(["###.", "#..#", "#.##", "###."]))  # a hole touching the outside at a corner
    assert sum(area(r) for r in found) == -11
    assert all(len(r) >= 4 for r in found)


def test_area_matches_cell_count_on_random_blobs():
    rng = np.random.default_rng(3)
    for _ in range(50):
        grid = rng.random((12, 15)) < 0.55
        picture = ["".join("#" if v else "." for v in row) for row in grid]
        runs = runs_of(picture)
        if runs:
            assert sum(area(r) for r in rings(runs)) == -int(grid.sum())
