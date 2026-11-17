"""Where packbuild finds the curated datasets: the placewise-data checkout beside this repo."""

from pathlib import Path

from packbuild import datasets


def test_default_is_the_sibling_placewise_data_checkout(monkeypatch):
    monkeypatch.delenv(datasets.ENV_DIR, raising=False)
    repo = Path(datasets.__file__).resolve().parents[1]
    assert datasets.root() == repo.parent / "placewise-data" / "datasets"


def test_environment_variable_overrides_it(monkeypatch, tmp_path):
    monkeypatch.setenv(datasets.ENV_DIR, str(tmp_path))
    assert datasets.root() == tmp_path
    assert datasets.path("regions", "usa.json") == tmp_path / "regions" / "usa.json"


def test_the_variable_is_not_a_placewise_runtime_setting():
    # placewise's config loader rejects unknown PLACEWISE_* variables
    assert not datasets.ENV_DIR.startswith("PLACEWISE_")
