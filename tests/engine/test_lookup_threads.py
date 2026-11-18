"""One Geocoder shared by threads (as the threaded HTTP server shares one) answers every lookup as
sequential lookups do, and stays correct afterwards: lazy caches are never seen half built."""

import json
import sys
import threading

import numpy as np
import pytest
from lookup_kit import write_ragged_world

from placewise.engine import Geocoder

THREADS = 8


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return write_ragged_world(tmp_path_factory.mktemp("threads"))


@pytest.fixture
def fast_switching():
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(old)


def _batches():
    rng = np.random.default_rng(81)
    out = []
    for _ in range(THREADS * 4):
        n = int(rng.integers(1, 40))
        out.append((rng.uniform(-0.1, 2.6, n), rng.uniform(-140.1, -137.9, n)))
    return out


def _answer(geo, batch):
    return json.dumps([r.to_dict() for r in geo.lookup_many(*batch)], sort_keys=True)


def test_threads_sharing_a_geocoder_answer_as_sequential_lookups(world, fast_switching):
    batches = _batches()
    want = [_answer(Geocoder(packs=[world]), b) for b in batches]
    geo = Geocoder(packs=[world])
    got, errors = {}, []

    def run(mine):
        try:
            for i in mine:
                got[i] = _answer(geo, batches[i])
        except Exception as err:  # reported below
            errors.append(err)

    threads = [threading.Thread(target=run, args=(range(t, len(batches), THREADS),)) for t in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert [got[i] for i in range(len(batches))] == want
    assert [_answer(geo, b) for b in batches] == want  # and the caches stay right
