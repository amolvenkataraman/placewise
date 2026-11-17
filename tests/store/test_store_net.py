"""placewise.store.net: downloads over HTTP from a server on 127.0.0.1."""

import json
import os

import pytest
from store_kit import LocalServer, Release, leftovers

import placewise
from placewise.constants import store as store_constants
from placewise.model import DataSettings
from placewise.store import DownloadError, Store


def test_install_over_http_with_mirror_fallback_and_generic_user_agent(data_dir, tmp_path):
    served = tmp_path / "served"
    Release(served / "release").add("world", "2026.11")
    with LocalServer(served) as server:
        store = Store(
            data_dir,
            DataSettings(mirrors=(server.url + "missing/index.json", server.url + "release/")),
            index_url=server.url + "also-missing/index.json",
        )
        assert store.install("world").name == "world-2026.11"
        assert set(server.user_agents) == {f"placewise/{placewise.__version__}"}
    cached = json.loads((data_dir / "index.json").read_text())
    assert cached["packs"]["world"]["url"] == server.url + "release/world-2026.11.tar.xz"


def test_http_download_size_limit(data_dir, tmp_path):
    served = tmp_path / "served"
    blob = os.urandom(store_constants.DOWNLOAD_SLACK_BYTES * 2)
    Release(served).add("world", "2026.11", files={"blob.bin": blob}, size=1000)
    with LocalServer(served) as server:
        store = Store(data_dir, index_url=server.url + "index.json")
        with pytest.raises(DownloadError, match=r"larger|size"):
            store.install("world")
    assert store.installed() == {}
    assert leftovers(data_dir) == []
