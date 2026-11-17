"""The source registry: one JSON file per purpose in src/placewise/sources/ (boundaries, places,
postal ...), each listing the sources used for that purpose in every region. Nothing in code."""

import json
import re
from pathlib import Path

import pytest

from placewise import attribution

PACKBUILD = Path(__file__).resolve().parents[1] / "packbuild"
ENTRY = {"id": "demo", "name": "Demo", "url": "https://example.org", "licence": "CC0-1.0", "credit": "Demo"}


def _write(folder, purpose, regions, **extra):
    doc = {"purpose": purpose, "description": f"{purpose} data", "regions": regions, **extra}
    (folder / f"{purpose}.json").write_text(json.dumps(doc), encoding="utf-8")


def test_each_file_is_one_purpose_listing_sources_per_region():
    registry = attribution.load_registry()
    assert {"boundaries", "places", "regions", "postal", "airports"} <= set(registry)
    for path in attribution.SOURCES_DIR.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["purpose"] == path.stem and doc["description"]
        assert all(re.fullmatch(r"world|[a-z]{2}", region) for region in doc["regions"])
    assert [s.id for s in registry["boundaries"]["world"]] == ["naturalearth"]
    assert [s.id for s in registry["airports"]["world"]] == ["ourairports"]
    # a source serves several purposes but only lists that purpose's downloads in each file
    assert set(registry["postal"]["us"][0].downloads) == {"zcta", "gazetteer_zcta"}


def test_the_folder_holds_only_purpose_files():
    assert {p.suffix for p in attribution.SOURCES_DIR.iterdir()} == {".json"}


def test_regions_without_a_usable_source_say_why():
    gaps = attribution.load_gaps()
    assert "in" in gaps["boundaries"] and gaps["boundaries"]["in"]
    for purpose, regions in attribution.load_registry().items():
        for region in gaps.get(purpose, {}):
            assert not regions.get(region), f"{purpose}/{region} has sources and a gap note"


def test_load_sources_merges_each_source_across_purposes():
    sources = attribution.load_sources()
    assert {"naturalearth", "geonames", "ourairports", "uscensus"} <= set(sources)
    assert sources["geonames"].licence == "CC-BY-4.0"
    census = sources["uscensus"].downloads
    assert {"state", "place", "cbsa", "zcta", "population"} <= set(
        census
    )  # boundaries + regions + postal + places
    assert attribution.source("naturalearth") is sources["naturalearth"]
    with pytest.raises(KeyError, match="nope"):
        attribution.source("nope")


def test_downloads_are_named_urls():
    for source in attribution.load_sources().values():
        for key, url in source.downloads.items():
            assert re.fullmatch(r"[a-z0-9_]+", key) and url.startswith("https://")


def test_a_denied_source_fails_the_licence_gate(tmp_path):
    _write(tmp_path, "boundaries", {"world": [{**ENTRY, "id": "gadm", "licence": "CC-BY-4.0"}]})
    with pytest.raises(ValueError, match="deny list"):
        attribution.load_sources(tmp_path)


def test_a_source_must_be_credited_the_same_way_everywhere(tmp_path):
    _write(tmp_path, "boundaries", {"world": [{**ENTRY, "downloads": {"a": "https://example.org/a"}}]})
    _write(tmp_path, "places", {"us": [{**ENTRY, "credit": "Something else"}]})
    with pytest.raises(ValueError, match=r"demo.*credit"):
        attribution.load_sources(tmp_path)


def test_a_download_name_means_one_url(tmp_path):
    _write(tmp_path, "boundaries", {"world": [{**ENTRY, "downloads": {"a": "https://example.org/a"}}]})
    _write(tmp_path, "places", {"world": [{**ENTRY, "downloads": {"a": "https://example.org/other"}}]})
    with pytest.raises(ValueError, match="'a'"):
        attribution.load_sources(tmp_path)


def test_a_file_must_name_its_own_purpose(tmp_path):
    _write(tmp_path, "boundaries", {})
    doc = json.loads((tmp_path / "boundaries.json").read_text())
    (tmp_path / "parks.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError, match=r"parks\.json"):
        attribution.load_registry(tmp_path)


def test_build_code_takes_every_url_from_the_registry():
    # every build module: world.py, us.py, ... and the per-source loaders
    for path in [*sorted((PACKBUILD / "sources").glob("*.py")), *sorted(PACKBUILD.glob("*.py"))]:
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
