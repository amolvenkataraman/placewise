"""`once` builds a value once per object however many threads ask; Guarded objects pickle."""

import pickle
import threading
import time

import numpy as np

from placewise.packs import PointIndex, once


class _Slow:
    def __init__(self):
        self.builds = 0

    @once
    def value(self):
        """A slow build."""
        self.builds += 1
        time.sleep(0.05)
        return [self.builds]


def test_once_builds_once_across_threads():
    obj = _Slow()
    seen = []
    threads = [threading.Thread(target=lambda: seen.append(obj.value)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert obj.builds == 1 and all(v is seen[0] for v in seen)
    assert _Slow.value.__doc__ == "A slow build."


def test_once_behaves_like_cached_property():
    obj = _Slow()
    assert obj.value == [1] and obj.value == [1]
    del obj.value  # forget it: built again on next use
    assert obj.value == [2]
    obj.value = "set"
    assert obj.value == "set"


def test_guarded_objects_pickle():
    rng = np.random.default_rng(3)
    index = PointIndex(rng.uniform(-60, 60, 200), rng.uniform(-170, 170, 200))
    index.nearest(0.0, 0.0, max_km=20_000)  # builds coarser grids
    copy = pickle.loads(pickle.dumps(index))
    for got, want in zip(copy.nearest(10.0, 20.0, k=3), index.nearest(10.0, 20.0, k=3), strict=True):
        np.testing.assert_array_equal(got, want)
