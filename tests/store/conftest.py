import pytest
from store_kit import Release


@pytest.fixture(autouse=True)
def _no_real_network_or_home(tmp_path, monkeypatch):
    # a test that forgets index_url or data_dir must fail locally, not reach GitHub or ~/.local
    monkeypatch.setenv("PLACEWISE_INDEX_URL", (tmp_path / "no-index-here" / "index.json").as_uri())
    monkeypatch.setenv("PLACEWISE_DATA_DIR", str(tmp_path / "env-data"))


@pytest.fixture
def release(tmp_path):
    return Release(tmp_path / "release")


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"
