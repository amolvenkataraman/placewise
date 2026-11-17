import pytest


@pytest.fixture(autouse=True)
def _empty_cwd(tmp_path, monkeypatch):
    """No ./placewise.toml from the developer's checkout leaks into a test."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
