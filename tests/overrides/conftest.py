"""Fixtures for the overrides tests."""

import pytest


@pytest.fixture
def empty_repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    return d
