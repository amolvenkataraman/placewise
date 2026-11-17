import pytest

from tests.store.store_kit import Release


@pytest.fixture(autouse=True)
def _no_real_network_home_or_keys(tmp_path, monkeypatch):
    # the same guards as tests/store and tests/service: a test that forgets index_url, data_dir or
    # --keys-file must fail locally, not reach GitHub, ~/.local or the real per-user keys file
    monkeypatch.setenv("PLACEWISE_INDEX_URL", (tmp_path / "no-index-here" / "index.json").as_uri())
    monkeypatch.setenv("PLACEWISE_DATA_DIR", str(tmp_path / "env-data"))
    monkeypatch.setenv("PLACEWISE_KEYS_FILE", str(tmp_path / "env-keys" / "keys.json"))


@pytest.fixture
def release(tmp_path):
    return Release(tmp_path / "release")


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"
