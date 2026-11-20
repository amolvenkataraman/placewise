"""lookup_many in chunks of distinct points: the same Results as one pass, bounded pass sizes."""

import numpy as np
import pytest
from lookup_kit import write_world

from placewise.constants import lookup as const
from placewise.engine import Geocoder


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    return Geocoder(packs=[write_world(tmp_path_factory.mktemp("chunks"))])


def _points(n=57, seed=7):
    rng = np.random.default_rng(seed)
    lat = rng.uniform(-0.5, 2.6, n)
    lon = rng.uniform(-140.5, -137.5, n)
    lat[10], lon[10] = lat[3], lon[3]  # a repeat across chunks
    return lat, lon


@pytest.mark.parametrize("near", [True, False])
def test_chunks_give_the_same_results_as_one_pass(geo, monkeypatch, near):
    lat, lon = _points()
    alt = np.where(np.arange(len(lat)) % 3 == 0, 5000.0, np.nan)
    alt[10] = alt[3]
    whole = geo.lookup_many(lat, lon, near=near, altitude_m=alt)
    passes = []
    run = geo._run

    def spy(lat, *args):
        passes.append(len(lat))
        return run(lat, *args)

    monkeypatch.setattr(const, "CHUNK_POINTS_NEAR", 10)
    monkeypatch.setattr(const, "CHUNK_POINTS", 10)
    monkeypatch.setattr(geo, "_run", spy)
    chunked = geo.lookup_many(lat, lon, near=near, altitude_m=alt)
    assert [r.to_dict() for r in chunked] == [r.to_dict() for r in whole]
    assert passes == [10, 10, 10, 10, 10, 6]  # 56 distinct points
    assert chunked[10] is chunked[3]


def test_small_batches_run_in_one_pass(geo, monkeypatch):
    passes = []
    run = geo._run
    monkeypatch.setattr(geo, "_run", lambda lat, *args: passes.append(len(lat)) or run(lat, *args))
    lat, lon = _points(40)
    geo.lookup_many(lat, lon)
    assert passes == [39]
    assert const.CHUNK_POINTS_NEAR >= 1000 and const.CHUNK_POINTS >= const.CHUNK_POINTS_NEAR
