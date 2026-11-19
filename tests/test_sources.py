"""The source registry: one JSON file per purpose in src/placewise/sources/ (boundaries, places,
postal ...), each listing the sources used for that purpose in every region. Nothing in code."""

import json
import re
from pathlib import Path

import pytest

from placewise import attribution
from placewise.constants.countries.countries import BY_ALPHA3
from placewise.constants.packs import MULTI_COUNTRY_REGIONS

PACKBUILD = Path(__file__).resolve().parents[1] / "packbuild"
ENTRY = {"id": "demo", "name": "Demo", "url": "https://example.org", "licence": "CC0-1.0", "credit": "Demo"}


def _write(folder, purpose, regions, **extra):
    doc = {"purpose": purpose, "description": f"{purpose} data", "regions": regions, **extra}
    (folder / f"{purpose}.json").write_text(json.dumps(doc), encoding="utf-8")


def test_each_file_is_one_purpose_listing_sources_per_region():
    registry = attribution.load_registry()
    assert {"boundaries", "places", "regions", "postal", "airports", "countries"} <= set(registry)
    for path in attribution.SOURCES_DIR.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["purpose"] == path.stem and doc["description"]
        assert all(
            region == "world" or region in MULTI_COUNTRY_REGIONS or region.upper() in BY_ALPHA3
            for region in doc["regions"]
        )
    assert [s.id for s in registry["boundaries"]["world"]] == ["naturalearth"]
    assert [s.id for s in registry["airports"]["world"]] == ["ourairports"]
    # a source serves several purposes but only lists that purpose's downloads in each file
    assert set(registry["postal"]["usa"][0].downloads) == {
        "zcta",
        "gazetteer_zcta",
        "zip_cities",
        "zcta_place",
    }


@pytest.mark.parametrize("region", ["us", "IND", "xyz", "world2", "EUR", "europe"])
def test_a_region_is_world_or_a_lower_case_iso_alpha3_code(tmp_path, region):
    # pack names and region keys are lower-case ISO 3166-1 alpha-3 (docs/code-structure.md), or a
    # named group of countries (constants.packs.MULTI_COUNTRY_REGIONS: "eur")
    _write(tmp_path, "places", {region: [ENTRY]})
    with pytest.raises(ValueError, match=f"region {region!r}"):
        attribution.load_registry(tmp_path)
    _write(tmp_path, "places", {"world": [ENTRY], "can": [ENTRY], "eur": [ENTRY]})
    assert set(attribution.load_registry(tmp_path)["places"]) == {"world", "can", "eur"}


def test_each_source_is_used_in_the_packs_of_the_regions_listing_it():
    # used_in names "<pack>/<layer>"; a region's sources go in that region's packs (or world's):
    # "<region>" or a topic pack "<region>-<topic>" ("world-water")
    for purpose, regions in attribution.load_registry().items():
        for region, sources in regions.items():
            for s in sources:
                packs = {e.split("/")[0] for e in s.used_in if not e.startswith("package:")}
                assert all(p.split("-")[0] in {"world", region} for p in packs), (
                    f"{purpose}/{region}: {s.id} used in {packs}"
                )


def test_the_folder_holds_only_purpose_files():
    assert {p.suffix for p in attribution.SOURCES_DIR.iterdir()} == {".json"}


def test_regions_without_a_usable_source_say_why():
    gaps = attribution.load_gaps()
    assert "ind" in gaps["parks"] and gaps["parks"]["ind"]
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
    _write(tmp_path, "places", {"usa": [{**ENTRY, "credit": "Something else"}]})
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
    # regenerate with: uv run placewise attribution --all > ATTRIBUTION.md
    assert (REPO / "ATTRIBUTION.md").read_text(encoding="utf-8") == attribution.render_markdown()


@pytest.mark.parametrize("only", [None, ["naturalearth"]])
def test_attribution_starts_with_the_disclaimer(only):
    text = attribution.render_markdown(only=only)
    title, first, *_ = text.split("\n\n")
    assert title == "# Data attribution"
    assert first.startswith("**Disclaimer.**") and '"as is" and "where is"' in first
    assert "[DISCLAIMER.md](DISCLAIMER.md)" in first and "liability" in first
    assert (REPO / "DISCLAIMER.md").is_file()


def test_credits_are_one_line_per_source():
    sources = attribution.load_sources()
    assert attribution.render_credits().splitlines() == [s.credit for s in sources.values()]
    assert attribution.render_credits(only=["geonames", "naturalearth"]) == (
        f"{sources['naturalearth'].credit}\n{sources['geonames'].credit}\n"  # registry order
    )
    with pytest.raises(KeyError, match="nope"):
        attribution.render_credits(only=["nope"])


def test_pack_sources_are_the_ids_packs_carry_in_order_without_repeats():
    class FakePack:
        def __init__(self, *sources):
            self.sources = sources

    packs = [FakePack("naturalearth", "geonames"), FakePack("uscensus", "geonames")]
    assert attribution.pack_sources(packs) == ("naturalearth", "geonames", "uscensus")
    assert attribution.pack_sources([]) == ()


def test_attribution_for_a_subset_lists_only_those_sources_and_their_regions():
    # a release's ATTRIBUTION.md: only the sources its packs use
    text = attribution.render_markdown(only=["naturalearth", "geonames"])
    assert "## Natural Earth" in text and "## GeoNames" in text
    assert "OurAirports" not in text and "Census" not in text
    assert "| boundaries | world | Natural Earth" in text and "| boundaries | usa |" not in text
    assert "placewise attribution" not in text  # not the generated whole-registry file
    assert attribution.render_markdown(only=["uscensus", "uscensus"]).count("## US Census") == 1
    with pytest.raises(KeyError, match="nope"):
        attribution.render_markdown(only=["naturalearth", "nope"])


def test_country_facts_list_their_sources():
    world = {s.id: s for s in attribution.load_registry()["countries"]["world"]}
    assert set(world) == {"geonames", "cldr", "wikidata", "naturalearth"}
    assert world["cldr"].licence == "Unicode-3.0" and world["wikidata"].licence == "CC0-1.0"
    assert all("/cldr-json/49.0.0/" in u for u in world["cldr"].downloads.values())  # a pinned release
    assert set(world["geonames"].downloads) == {"country_info", "time_zones", "cities"}
    assert all("world/country_facts" in s.used_in for s in world.values())
