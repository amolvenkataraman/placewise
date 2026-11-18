"""Concurrent queries on one opened layer give the answers sequential ones give, and leave its lazy
caches (slabs, fine grids, memos, edge caps, boundary index) as sequential use would."""

import sys
import threading

import numpy as np
import pytest
from pack_kit import CREATED, blob_features, polygon_layer

from placewise.packs import open_pack, write_pack

THREADS = 8
ROUNDS = 40


@pytest.fixture
def fast_switching():
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # switch threads as often as possible: races show up at once
    yield
    sys.setswitchinterval(old)


def _pack(tmp_path):
    rng = np.random.default_rng(71)
    features = blob_features(60, rng, radius=(0.5, 3.0), vertices=(200, 900), lat_range=(-40, 40), holes=True)
    path = write_pack(tmp_path, "test", "2026.11", [polygon_layer(features, cell_deg=1.0)], created=CREATED)
    return path


def _points(seed, n):
    rng = np.random.default_rng(seed)
    return rng.uniform(-45, 45, n), rng.uniform(-175, 175, n)


def _work(layer, seed):
    """Small, varied calls: each adds a little to the caches, as single lookups do."""
    lat, lon = _points(seed, 600)
    out = []
    for i in range(0, len(lat), 15):
        la, lo = lat[i : i + 15], lon[i : i + 15]
        found = layer.query(la, lo)
        out.append(found)
        out.append(layer.contains(la, lo, np.maximum(found, 0)))
        out.append(layer.nearest_edge_km(la, lo, (np.arange(len(la)) * 7 + seed) % layer.count))
        out.extend(layer.near_boundary(la, lo, 20.0))
    return out


def _same(a, b):
    return len(a) == len(b) and all(np.array_equal(x, y) for x, y in zip(a, b, strict=True))


def test_threads_on_one_layer_answer_as_sequential_calls(tmp_path, fast_switching):
    path = _pack(tmp_path)
    seeds = list(range(THREADS * 3))
    reference = open_pack(path)["areas"]
    want = {s: _work(reference, s) for s in seeds}

    shared = open_pack(path)["areas"]
    got, errors = {}, []

    def run(my_seeds):
        try:
            for s in my_seeds:
                got[s] = _work(shared, s)
        except Exception as err:
            errors.append(err)

    threads = [threading.Thread(target=run, args=(seeds[t::THREADS],)) for t in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    wrong = [s for s in seeds if not _same(got[s], want[s])]
    assert not wrong, f"{len(wrong)} of {len(seeds)} concurrent batches differ"
    # and the caches the threads built answer correctly afterwards
    after = [s for s in seeds if not _same(_work(shared, s), want[s])]
    assert not after, f"{len(after)} batches differ after the concurrent run"
