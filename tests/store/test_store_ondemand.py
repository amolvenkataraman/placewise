"""placewise.store.ondemand: which packs a batch of points or a search needs, and fetching them in
auto mode (once, under a lock, with a log line); manual and locked never download. No network:
releases are file:// directories, and the locked tests make any fetch fail loudly."""

import logging
import threading

import pytest
from store_kit import make_store

from placewise.store import net


def _auto_store(data_dir, release, **settings):
    """A store in auto mode unless the test says otherwise (manual is the default since 2026-11-18)."""
    return make_store(data_dir, release, **{"mode": "auto", **settings})


PACKS = {
    "world": {},
    "usa": {"installed_bytes": 96_000_000},
    "can": {},
    "ind": {},
    "usa-parks": {},
    "can-parks": {},
    "world-water": {},
    "world-parks": {},
    "usa-zip": {"kind": "postal", "covers": ["US"], "requires": ["usa"]},
}


@pytest.fixture
def full_release(release):
    for name, meta in PACKS.items():
        release.add(name, "2026.11", meta=meta)
    return release


@pytest.fixture
def no_network(monkeypatch):
    def refuse(url):
        raise AssertionError(f"tried to fetch {url}")

    monkeypatch.setattr(net, "_open", refuse)


def test_auto_plans_only_country_packs_by_default(data_dir, full_release):
    store = _auto_store(data_dir, full_release)
    assert store.plan(countries={"US"}) == ["usa"]
    assert store.plan(countries={"US", "CA"}) == ["can", "usa"]
    assert store.plan(countries={"FR"}) == []


def test_opted_in_kinds_add_their_packs_requirements_first(data_dir, full_release):
    store = _auto_store(data_dir, full_release, auto_packs=("country", "parks", "water", "postal"))
    assert store.plan(countries={"US"}) == ["usa", "usa-parks", "usa-zip", "world-parks", "world-water"]
    # usa-zip alone still brings the usa pack it needs
    store = _auto_store(data_dir, full_release, auto_packs=("postal",))
    assert store.plan(countries={"US"}) == ["usa", "usa-zip"]


def test_a_search_kind_is_an_opt_in_for_that_search(data_dir, full_release):
    store = _auto_store(data_dir, full_release)
    assert store.plan(countries={"CA"}, extra_kinds={"parks"}) == ["can", "can-parks", "world-parks"]
    assert store.plan(extra_kinds={"parks"}) == ["world-parks"]  # no country: world-wide packs only


def test_a_pack_for_a_group_of_countries_serves_the_countries_it_covers(data_dir, release):
    for name, meta in PACKS.items():
        release.add(name, "2026.11", meta=meta)
    release.add("eur-parks", "2026.11", meta={"kind": "parks", "covers": ["AT", "DE", "HR"]})
    store = _auto_store(data_dir, release, auto_packs=("country", "parks"))
    assert store.plan(countries={"AT"}) == ["eur-parks", "world-parks"]
    assert store.plan(countries={"FR"}) == ["world-parks"]  # not a country it covers
    from placewise.constants.lookup import OPTIONAL_PACKS

    assert "eur-parks" in OPTIONAL_PACKS  # the Geocoder reads it, so auto mode may fetch it


def test_installed_and_unusable_packs_are_not_planned(data_dir, full_release):
    store = _auto_store(data_dir, full_release)
    store.install("usa")
    assert store.plan(countries={"US", "CA"}) == ["can"]
    assert store.plan(countries={"US", "CA"}, usable={"world", "usa"}) == []


def test_auto_fetches_once_and_logs_the_size(data_dir, full_release, caplog):
    store = _auto_store(data_dir, full_release)
    with caplog.at_level(logging.INFO, logger="placewise.store"):
        paths = store.fetch_for(countries={"US"})
    assert [p.name for p in paths] == ["usa-2026.11"]
    assert store.installed().keys() >= {"usa"}
    line = next(r.getMessage() for r in caplog.records if "usa" in r.getMessage())
    assert "downloading" in line and "US" in line and "96.0 MB" in line
    assert store.fetch_for(countries={"US"}) == []


def test_concurrent_batches_download_a_pack_once(data_dir, full_release, monkeypatch):
    store = _auto_store(data_dir, full_release)
    calls = []
    real = net.fetch_file

    def counting(url, *args, **kwargs):
        calls.append(url)
        return real(url, *args, **kwargs)

    monkeypatch.setattr(net, "fetch_file", counting)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(store.fetch_for(countries={"CA"}))) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert sorted(len(r) for r in results) == [0, 0, 0, 1]


def test_a_failed_download_is_logged_once_and_not_retried(data_dir, full_release, caplog):
    (full_release.root / "can-2026.11.tar.xz").write_bytes(b"not the archive")
    store = _auto_store(data_dir, full_release)
    with caplog.at_level(logging.WARNING, logger="placewise.store"):
        assert store.fetch_for(countries={"CA"}) == []
        assert store.fetch_for(countries={"CA"}) == []
    failures = [r for r in caplog.records if "couldn't install can" in r.getMessage()]
    assert len([r for r in caplog.records if "downloading can" in r.getMessage()]) == 1
    assert len(failures) == 1
    assert store.wants(usable={"world", "can"}) is False  # nothing left worth checking points for


def test_manual_never_downloads_and_hints_once(data_dir, full_release, caplog):
    _auto_store(data_dir, full_release).fetch_index()  # a cached index, as after `data list`
    store = _auto_store(data_dir, full_release, mode="manual")
    with caplog.at_level(logging.INFO, logger="placewise.store"):
        assert store.fetch_for(countries={"US"}) == []
        assert store.fetch_for(countries={"US"}) == []
    hints = [r.getMessage() for r in caplog.records if "placewise data install usa" in r.getMessage()]
    assert len(hints) == 1
    assert "usa" not in store.installed()


def test_manual_without_a_cached_index_stays_quiet_and_offline(data_dir, full_release, no_network):
    store = _auto_store(data_dir, full_release, mode="manual")
    assert store.fetch_for(countries={"US"}) == []
    assert store.wants() is False


@pytest.mark.parametrize(
    "settings", [{"mode": "locked"}, {"offline": True}, {"mode": "auto", "offline": True}]
)
def test_locked_never_touches_the_network(data_dir, full_release, no_network, settings):
    store = _auto_store(data_dir, full_release, **settings)
    assert store.fetch_for(countries={"US", "CA"}, extra_kinds={"parks"}) == []
    assert store.plan(countries={"US"}) == []  # no cached index: nothing known, nothing fetched
    assert not (data_dir / "packs").exists()


def test_locked_with_a_cached_index_still_never_downloads(data_dir, full_release, monkeypatch):
    _auto_store(data_dir, full_release).fetch_index()
    store = _auto_store(data_dir, full_release, mode="locked")

    def refuse(url):
        raise AssertionError(f"tried to fetch {url}")

    monkeypatch.setattr(net, "_open", refuse)
    assert store.fetch_for(countries={"US"}) == []
    assert "usa" not in store.installed()


def test_auto_plans_from_a_fresh_cached_index_without_the_network(data_dir, full_release, monkeypatch):
    store = _auto_store(data_dir, full_release)
    store.install("usa")
    later = _auto_store(data_dir, full_release)
    opened = []
    real = net._open
    monkeypatch.setattr(net, "_open", lambda url: opened.append(url) or real(url))
    assert later.fetch_for(countries={"US"}) == []
    assert opened == []


def test_wants_says_whether_points_are_worth_a_country_check(data_dir, full_release):
    store = _auto_store(data_dir, full_release)
    assert store.wants()
    for name in ("usa", "can", "ind"):
        store.install(name)
    assert not store.wants()
    assert not store.wants(usable={"world"})


def test_install_brings_the_packs_a_pack_requires(data_dir, full_release):
    store = _auto_store(data_dir, full_release)
    store.install("usa-zip")
    assert {"usa", "usa-zip"} <= store.installed().keys()


def test_pending_names_the_countries_a_missing_pack_serves(data_dir, full_release):
    store = _auto_store(data_dir, full_release)
    assert store.pending() == {"US", "CA", "IN"}
    store.install("usa")
    assert store.pending() == {"CA", "IN"}
    assert "*" in _auto_store(data_dir, full_release, auto_packs=("water",)).pending()
