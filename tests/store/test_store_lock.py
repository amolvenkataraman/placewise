"""placewise.store.lock: the data-directory lock, as installs see it.
No network: packs are served from file:// URLs."""

import os
import re
import threading
import time

import pytest
from store_kit import leftovers, make_store

from placewise.constants import store as store_constants
from placewise.store import LockError


def test_a_held_lock_blocks_install_until_timeout(data_dir, release, monkeypatch):
    release.add("world", "2026.11")
    monkeypatch.setattr(store_constants, "LOCK_WAIT_S", 0.3)
    store = make_store(data_dir, release)
    data_dir.mkdir(parents=True)
    lock = store.layout.lock
    lock.write_text("12345")
    with pytest.raises(LockError, match=re.escape(str(lock))):
        store.install("world")
    assert store.installed() == {}
    assert lock.exists()  # someone else's lock is not ours to delete


def test_a_stale_lock_is_broken(data_dir, release):
    release.add("world", "2026.11")
    store = make_store(data_dir, release)
    data_dir.mkdir(parents=True)
    store.layout.lock.write_text("12345")
    old = time.time() - store_constants.LOCK_STALE_S - 10
    os.utime(store.layout.lock, (old, old))
    assert store.install("world").is_dir()
    assert not store.layout.lock.exists()


def test_concurrent_installs_do_not_collide(data_dir, release):
    release.add("world", "2026.11")
    results, errors = [], []

    def worker():
        try:
            results.append(make_store(data_dir, release).install("world"))
        except Exception as e:  # pragma: no cover - surfaced by the assert below
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(set(results)) == 1
    assert make_store(data_dir, release).verify() == []
    assert leftovers(data_dir) == []
