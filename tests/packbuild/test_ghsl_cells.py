"""Settlement cells and their 4-connected clusters (packbuild.sources.ghsl.cells)."""

import numpy as np
from ghsl_kit import write_tiff

from packbuild.sources.ghsl.cells import clusters, read_cells
from packbuild.sources.ghsl.geotiff import GeoTiff

GRID = np.array(
    [
        [10, 30, 30, 10, 23, 10],
        [10, 30, 10, 10, 22, 21],
        [30, 10, 10, 10, 10, 10],
        [30, 30, 30, 10, 23, 23],
    ],
    dtype=np.int16,
)
GROUPS = {30: 0, 23: 1, 22: 1}


def cells():
    return read_cells(GeoTiff(write_tiff(GRID, tile=(4, 4), compression=5, predictor=2)), GROUPS)


def test_read_cells_keeps_only_the_groups_in_row_order():
    c = cells()
    assert list(zip(c.row.tolist(), c.col.tolist(), c.group.tolist(), strict=True)) == [
        (0, 1, 0), (0, 2, 0), (0, 4, 1), (1, 1, 0), (1, 4, 1), (2, 0, 0), (3, 0, 0), (3, 1, 0), (3, 2, 0),
        (3, 4, 1), (3, 5, 1),
    ]  # fmt: skip
    assert c.find([0, 1, 3], [2, 2, 5]).tolist() == [1, -1, 10]


def test_clusters_are_four_connected_and_split_by_key():
    c = cells()
    found = clusters(c, c.group)
    # the centre cells at (1,1) and (2,0) touch only at a corner: two clusters
    assert found.count == 4
    members = found.members()
    sizes = sorted(int((found.c1[m] - found.c0[m]).sum()) for m in members)
    assert sizes == [2, 2, 3, 4]
    assert found.runs(0) == [(0, 1, 3), (1, 1, 2)]
    # a key that differs inside a run (a border) splits the run and the cluster
    key = c.group.astype(np.int64) * 10 + (c.col >= 2)
    split = clusters(c, key)
    assert split.count == 6
    assert split.label[split.run_of_cell].shape == (len(c.row),)


def test_no_cells():
    c = cells().subset(np.zeros(11, dtype=bool))
    assert clusters(c, c.group).count == 0
