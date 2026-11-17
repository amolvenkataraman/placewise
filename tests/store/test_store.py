"""placewise.store.store: the Store itself: where the index comes from, what's installed and which
version is current."""

import pytest
from store_kit import install_versions, make_store

import placewise
from placewise.constants import store as store_constants
from placewise.model import DataSettings
from placewise.store import PackNotInstalled, Store


def test_index_url_comes_from_argument_then_settings_then_env(data_dir, release, monkeypatch):
    release.add("world", "2026.11")
    assert Store(data_dir, DataSettings(index_url=release.index_url)).index_url == release.index_url
    monkeypatch.setenv("PLACEWISE_INDEX_URL", release.index_url)
    assert Store(data_dir).index_url == release.index_url
    assert (
        Store(data_dir, index_url="file:///elsewhere/index.json").index_url == "file:///elsewhere/index.json"
    )
    monkeypatch.delenv("PLACEWISE_INDEX_URL")
    assert Store(data_dir).index_url == store_constants.DEFAULT_INDEX_URL


def test_default_index_url_and_user_agent_are_generic():
    assert store_constants.DEFAULT_INDEX_URL.startswith("https://")
    assert (
        store_constants.USER_AGENT.format(version=placewise.__version__)
        == f"placewise/{placewise.__version__}"
    )


def test_current_is_the_newest_installed(data_dir, release):
    store = install_versions(data_dir, release, "2026.10", "2026.10.2", "2026.10.10")
    # numeric order, not string order
    assert store.installed() == {"world": ["2026.10", "2026.10.2", "2026.10.10"]}
    assert store.current("world").name == "world-2026.10.10"


def test_pin_holds_a_version(data_dir, release):
    install_versions(data_dir, release, "2026.10", "2026.11")
    assert make_store(data_dir, release, pin="2026.10").current("world").name == "world-2026.10"
    with pytest.raises(PackNotInstalled) as err:
        make_store(data_dir, release, pin="2026.09").current("world")
    assert "world" in str(err.value) and "placewise data install world --version 2026.09" in str(err.value)


def test_not_installed_names_the_install_command(data_dir, release):
    with pytest.raises(PackNotInstalled) as err:
        make_store(data_dir, release).current("world")
    assert "placewise data install world" in str(err.value)
    assert err.value.name == "world"
