"""The source registry: one JSON file per dataset in src/placewise/sources/, nothing in code."""

import json
import re
from pathlib import Path

import pytest

from placewise import attribution
from placewise.model import Source

PACKBUILD = Path(__file__).resolve().parents[1] / "packbuild"


def test_every_file_is_a_valid_source_named_after_its_id():
    files = sorted(attribution.SOURCES_DIR.glob("*.json"))
    assert files, "no sources found"
    for path in files:
        source = Source.from_dict(json.loads(path.read_text(encoding="utf-8")))  # the licence gate
        assert path.stem == source.id


def test_the_folder_holds_only_source_files():
    assert {p.suffix for p in attribution.SOURCES_DIR.iterdir()} == {".json"}


def test_load_sources_returns_every_source_by_id():
    sources = attribution.load_sources()
    assert {"naturalearth", "geonames", "ourairports"} <= set(sources)
    assert sources["geonames"].licence == "CC-BY-4.0"
    assert attribution.source("naturalearth") is sources["naturalearth"]
    with pytest.raises(KeyError, match="nope"):
        attribution.source("nope")


def test_downloads_are_named_urls():
    for source in attribution.load_sources().values():
        for key, url in source.downloads.items():
            assert re.fullmatch(r"[a-z0-9_]+", key) and url.startswith("https://")


def test_a_bad_file_fails_the_licence_gate(tmp_path):
    (tmp_path / "gadm.json").write_text(
        json.dumps(
            {
                "id": "gadm",
                "name": "GADM",
                "url": "https://gadm.org",
                "licence": "CC-BY-4.0",
                "credit": "GADM",
            }
        )
    )
    with pytest.raises(ValueError, match="deny list"):
        attribution.load_sources(tmp_path)


def test_build_code_takes_every_url_from_the_registry():
    for path in [*sorted((PACKBUILD / "sources").glob("*.py")), PACKBUILD / "world.py"]:
        code = re.sub(r"#.*", "", path.read_text(encoding="utf-8"))  # links in comments are fine
        assert not re.search(r"""["']https?://""", code), f"{path.name} hardcodes a URL"


REPO = Path(__file__).resolve().parents[1]


def test_attribution_file_lists_every_source_with_licence_and_credit():
    text = attribution.render_markdown()
    for s in attribution.load_sources().values():
        assert s.name in text and s.licence in text and s.credit in text and s.url in text


def test_committed_attribution_file_is_up_to_date():
    # regenerate with: uv run placewise attribution > ATTRIBUTION.md
    assert (REPO / "ATTRIBUTION.md").read_text(encoding="utf-8") == attribution.render_markdown()


def test_cli_prints_the_attribution(capsys):
    from placewise.cli import main

    assert main(["attribution"]) == 0
    assert capsys.readouterr().out == attribution.render_markdown()
    assert main(["attribution", "--json"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == set(attribution.load_sources())
