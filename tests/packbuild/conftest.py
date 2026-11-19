"""Shared by the packbuild tests."""

import pytest


@pytest.fixture(autouse=True)
def _own_downloads(monkeypatch):
    """Each test tracks only its own downloads (packbuild.fetch.track), so a builder's main run by
    one test (some use the default cache) never deletes what another test fetched."""
    from packbuild import fetch

    monkeypatch.setattr(fetch, "_FETCHED", {})
