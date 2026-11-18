"""The notable-place sources: the kind allowlist and its queries, the TSV reader, QRank."""

import urllib.parse

import notable_fixtures as fx
import pytest

from packbuild.sources import SOURCES
from packbuild.sources.notable import kinds, qrank, wikidata
from placewise.constants import notable as const
from placewise.model import PlaceKind


def test_every_kind_is_known_to_the_engine():
    assert [k.name for k in kinds.KINDS] == list(const.KINDS)
    for place_kind in const.KINDS.values():
        PlaceKind(place_kind)


def test_registry_urls_are_the_generated_queries():
    downloads = SOURCES["wikidata"].downloads
    for kind in kinds.KINDS:
        assert downloads[kinds.download_name(kind)] == kinds.url(kind), (
            f"paste kinds.url({kind.name!r}) into sources/notable.json"
        )


def test_query_text():
    airport = kinds.query(kinds.BY_NAME["airport"])
    assert "VALUES ?root { wd:Q1248784 }" in airport
    assert "?item wdt:P238 ?req0 ." in airport  # scheduled airports only: an IATA code
    assert "(MIN(?iata0_) AS ?iata0)" in airport and "OPTIONAL { ?item wdt:P239 ?icao0_ }" in airport
    park = kinds.query(kinds.BY_NAME["park"])
    assert "MINUS { ?item wdt:P31/wdt:P279* wd:Q473972 }" in park  # protected areas: the park packs
    assert "MINUS { ?item wdt:P576 ?end }" in park and "FILTER(?sitelinks >= 1)" in park
    url = kinds.url(kinds.BY_NAME["park"])
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query == {"action": ["tsv_export"], "query": [park]}


def test_station_codes_take_the_first_property_found():
    station = kinds.BY_NAME["station"]
    assert [v for v, _ in kinds.code_variables(station)] == [f"station_code{i}" for i in range(4)]


@pytest.mark.parametrize(
    ("cell", "value"),
    [
        ('"Eiffel Tower"@en', "Eiffel Tower"),
        ('"O\\"Hare \\\\ \\u00e9t\\u00E9"@en-gb', 'O"Hare \\ été'),
        ('"22"^^<http://www.w3.org/2001/XMLSchema#int>', "22"),
        ('"JGS|Ji\'an Airport"', "JGS|Ji'an Airport"),
        ("<http://www.wikidata.org/entity/Q243>", "<http://www.wikidata.org/entity/Q243>"),
        ("17", "17"),
    ],
)
def test_tsv_values(cell, value):
    assert wikidata.value(cell) == value


def test_kind_items_skip_rows_without_a_usable_label_or_point(tmp_path):
    station = kinds.BY_NAME["station"]
    path = fx.write_export(tmp_path / "s.tsv", station, [
        dict(qid="Q1", label="Good  Station", lon=-139.5, lat=0.5, countries="XA|xb", aliases="GS|Good",
             station_code1="gsa", station_code3="G"),
        dict(qid="Q2", label="Q2", lon=-139.5, lat=0.5),
        dict(qid="Q3", label="Off Earth", lon=-200.0, lat=0.5),
    ])  # fmt: skip
    found = list(wikidata.kind_items(station, path))
    assert len(found) == 1
    item = found[0]
    assert (item.qid, item.name, item.lat, item.lon, item.kind) == (
        "Q1",
        "Good Station",
        0.5,
        -139.5,
        "station",
    )
    assert item.countries == {"XA", "XB"} and item.aliases == ["GS", "Good"]
    assert item.codes == {"station_code": "GSA"}  # Amtrak's before the generic code, upper case


def test_read_takes_the_first_kind_and_gathers_the_rest(tmp_path):
    paths = {}
    for name in ("museum", "landmark"):
        paths[name] = fx.write_export(tmp_path / f"{name}.tsv", kinds.BY_NAME[name], fx.ROWS[name])
    items = wikidata.read(paths)
    museum = items["Q3"]
    assert museum.kind == "museum"  # museum comes before landmark in KINDS
    assert museum.aliases == ["The Alpha Museum", "alphamuseum.org", "AM"]
    assert items["Q4"].kind == "landmark" and items["Q6"].countries == {"XA", "XB"}


def test_qrank_reads_only_the_wanted_items(tmp_path):
    path = fx.write_qrank(tmp_path / "qrank-20261115.csv.gz", {"Q1": 10, "Q22": 5, "Q3": 7})
    assert qrank.pageviews(path, ["Q1", "Q3", "Q99"]) == {"Q1": 10, "Q3": 7}
    bad = tmp_path / "bad.csv"
    bad.write_text("Item,Views\nQ1,3\n")
    with pytest.raises(ValueError, match="header"):
        qrank.pageviews(bad, ["Q1"])


def test_a_cached_result_of_another_query_is_fetched_again(tmp_path, monkeypatch):
    fx.write_cache(tmp_path)
    museum = tmp_path / "notable-museum" / "wikidata"
    museum.with_name("wikidata.json").write_text('{"url": "https://example.org/old-query"}')
    calls = []

    def fake_fetch(url, folder, refresh=False, timeout=None):
        calls.append((folder.name, refresh))
        return folder / "wikidata"

    monkeypatch.setattr(wikidata, "fetch_file", fake_fetch)
    wikidata.fetch(tmp_path)
    assert ("notable-museum", True) in calls
    assert ("notable-station", False) in calls
