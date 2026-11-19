import json
import math

import numpy as np
import pytest
from names_kit import CITIES, names_data, names_layers, names_pack
from pack_kit import CREATED, point_layer

from placewise.constants import names as nc
from placewise.geo import haversine
from placewise.packs import Candidates, NameData, open_pack, write_pack


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    return names_pack(tmp_path_factory.mktemp("names"))


def _rows(c, idx):
    return [(idx.layers[layer], int(row)) for layer, row in zip(c.layer, c.row, strict=True)]


def test_a_pack_without_names_has_no_index(tmp_path):
    path = write_pack(tmp_path, "plain", "2026.11", [point_layer([1.0], [2.0])], created=CREATED)
    assert open_pack(path).names is None


def test_names_files_are_in_the_manifest_and_verify(pack):
    files = pack.manifest["files"]
    assert "names/names.json" in files
    assert any(f.startswith("names/inside/parks") for f in files)
    pack.verify()
    meta = json.loads((pack.path / "names" / "names.json").read_text())
    assert meta["format"] == nc.NAMES_FORMAT
    assert meta["layers"] == ["cities", "admin1", "parks", "airports"]
    assert "names" not in pack.manifest["layers"]


def test_exact_returns_every_feature_of_a_name_by_rank(pack):
    idx = pack.names
    c = idx.exact("Springfield")
    assert isinstance(c, Candidates)
    assert _rows(c, idx) == [("cities", 0), ("cities", 1)]  # 170k before 115k
    assert (c.match_score == 1).all()
    assert (c.name_kind == nc.OFFICIAL).all()
    assert [nc.PLACE_KINDS[k] for k in c.kind] == ["locality", "locality"]
    assert c.rank[0] > c.rank[1]
    assert idx.key(int(c.entry[0])) == "springfield"
    assert len(idx.exact("Springfield", limit=1)) == 1


def test_exact_normalises_like_city_key(pack):
    idx = pack.names
    assert _rows(idx.exact("ST. PAUL"), idx) == [("cities", 5)]
    assert _rows(idx.exact("saint paul"), idx) == [("cities", 5)]
    assert len(idx.exact("Nowhere")) == 0
    assert len(idx.exact("")) == 0


def test_aliases_are_names(pack):
    idx = pack.names
    c = idx.exact("Bombay")
    assert _rows(c, idx) == [("cities", 4)]
    assert c.name_kind.tolist() == [nc.ALIAS]
    assert _rows(idx.exact("t.o."), idx) == [("cities", 2)]


def test_codes_are_exact_only_and_apart_from_names(pack):
    idx = pack.names
    assert len(idx.exact("YYZ")) == 0
    assert _rows(idx.codes("yyz"), idx) == [("airports", 0)]
    assert _rows(idx.codes("CYYZ"), idx) == [("airports", 0)]
    assert _rows(idx.codes("CA-ON"), idx) == [("admin1", 0)]
    assert _rows(idx.codes("iso:CA-ON"), idx) == [("admin1", 0)]
    assert _rows(idx.codes("synthetic:park:0"), idx) == [("parks", 0)]
    assert (idx.codes("YOSE").name_kind == nc.CODE).all()
    assert len(idx.codes("Toronto")) == 0
    assert len(idx.codes("YY")) == 0  # no prefix matching


def test_wikidata_prefix_finds_bare_qids(tmp_path):
    layer = point_layer([1.0], [2.0])
    names = NameData.from_rows([("Q42", "spots", 0, "landmark", 0.5, "code")])
    idx = open_pack(write_pack(tmp_path, "q", "2026.11", [layer], created=CREATED, names=names)).names
    assert len(idx.codes("Q42")) == 1
    assert len(idx.codes("wikidata:Q42")) == 1


def test_prefix_one_per_feature_by_rank(pack):
    idx = pack.names
    assert _rows(idx.prefix("Mississ"), idx) == [("cities", 3)]
    c = idx.prefix("to")
    assert _rows(c, idx) == [("cities", 2), ("airports", 0)]
    assert c.match_score[1] == pytest.approx(2 / len("toronto pearson international airport"))
    assert c.match_score[0] == 1  # its alias "T.O." is the key "to"
    assert len(idx.prefix("s", limit=2)) == 2
    many = idx.prefix("s", limit=50)
    assert len(set(_rows(many, idx))) == len(many)  # one candidate per feature
    assert (np.diff(many.rank) <= 0).all()
    assert len(idx.prefix("zzz")) == 0
    assert len(idx.prefix("")) == 0


def test_prefix_never_returns_codes(pack):
    assert len(pack.names.prefix("yy")) == 0


def test_fuzzy_finds_typos(pack):
    idx = pack.names
    for typo, expected in [
        ("Torono", ("cities", 2)),
        ("Missisauga", ("cities", 3)),
        ("Yosemit", ("parks", 0)),
        ("Sprinfgield", ("cities", 0)),  # a transposition
    ]:
        c = idx.fuzzy(typo)
        assert _rows(c, idx)[0] == expected, typo
        assert 0 < c.match_score[0] < 1
    c = idx.fuzzy("Missisauga")
    assert c.match_score[0] == pytest.approx(1 - 1 / len("mississauga"))


def test_the_fuzzy_postings_are_stored_packed_and_read_without_building(pack, monkeypatch):
    from placewise.packs._names import match as _name_match

    files = pack.manifest["files"]
    for name in nc.TRIGRAM_FILES:
        assert f"names/{name}" in files
    fresh = open_pack(pack.path)

    def no_build(table):
        raise AssertionError("built in memory")

    monkeypatch.setattr(_name_match.Trigrams, "build", no_build)
    assert isinstance(fresh.names._trigrams, _name_match.PackedTrigrams)
    assert _rows(fresh.names.fuzzy("Torono"), fresh.names)[0] == ("cities", 2)


def test_a_pack_without_stored_postings_builds_them_with_the_same_answers(tmp_path):
    from placewise.packs._names import match as _name_match

    path = names_pack(tmp_path).path
    stored = open_pack(path).names
    for name in nc.TRIGRAM_FILES:
        (path / "names" / name).unlink()
    built = open_pack(path).names
    assert type(built._trigrams) is _name_match.Trigrams
    for text in ("Torono", "Missisauga", "Yosemit", "Sprinfgield", "Springfield", "Pari", "qqqq"):
        a, b = stored.fuzzy(text, limit=20), built.fuzzy(text, limit=20)
        for field in a.__slots__:
            np.testing.assert_array_equal(getattr(a, field), getattr(b, field))


def test_fuzzy_exact_text_scores_one_and_dedupes_features(pack):
    idx = pack.names
    c = idx.fuzzy("Springfield", limit=5)
    assert _rows(c, idx)[:2] == [("cities", 0), ("cities", 1)]
    assert (c.match_score[:2] == 1).all()
    assert len(set(_rows(c, idx))) == len(c)
    assert len(idx.fuzzy("qqqqqqqq")) == 0
    assert len(idx.fuzzy("")) == 0


def test_candidate_points_and_radii(pack):
    idx = pack.names
    c = idx.exact("Toronto")
    assert (c.lat[0], c.lon[0]) == pytest.approx((43.65, -79.38))
    # a disc of 2000 people per km2
    assert c.radius_km[0] == pytest.approx(math.sqrt(2_800_000 / 2000 / math.pi), rel=1e-5)
    park = idx.exact("Yosemite")
    assert pack["parks"].contains(park.lat[0], park.lon[0], 0)
    corners = [(37.5, -120.0), (38.2, -120.0), (37.5, -119.2)]
    far = max(haversine(park.lat[0], park.lon[0], a, b) for a, b in corners)
    assert park.radius_km[0] == pytest.approx(far, rel=1e-4)
    ontario = idx.exact("Ontario")
    assert pack["admin1"].contains(ontario.lat[0], ontario.lon[0], 0)


def test_label_points_are_used_when_inside(tmp_path):
    layers = names_layers()
    data = names_data(layers)
    data.points = {"admin1": (np.array([50.0, 50.0]), np.array([-80.0, -80.0]))}  # 2nd is outside
    idx = open_pack(write_pack(tmp_path, "pts", "2026.11", layers, created=CREATED, names=data)).names
    c = idx.exact("Ontario")
    assert (c.lat[0], c.lon[0]) == pytest.approx((50.0, -80.0))
    c = idx.exact("Missouri")
    assert pack_contains(tmp_path / "pts-2026.11", "admin1", c.lat[0], c.lon[0], 1)
    assert (c.lat[0], c.lon[0]) != pytest.approx((50.0, -80.0))


def pack_contains(path, layer, lat, lon, row):
    return open_pack(path)[layer].contains(lat, lon, row)


def test_resolve_point_and_polygon(pack):
    idx = pack.names
    r = idx.resolve("cities", 2)
    assert (r.layer, r.row, r.id, r.name) == ("cities", 2, "synthetic:city:2", "Toronto")
    assert r.columns["population"] == 2_800_000
    assert r.outlines == ()
    assert r.bbox.contains(r.lat, r.lon)
    assert r.bbox.north - r.lat == pytest.approx(r.radius_km / 111.195, rel=1e-3)
    p = idx.resolve(idx.layers.index("parks"), 0)
    assert p.name == "Yosemite National Park" and p.outlines == ()
    assert p.bbox.as_tuple() == pytest.approx((37.5, -120.0, 38.2, -119.2))
    with_outlines = idx.resolve("parks", 0, outlines=True)
    assert len(with_outlines.outlines) == 1
    assert with_outlines.outlines[0].contains(p.lat, p.lon)
    c = idx.exact("Yosemite")
    assert (p.lat, p.lon, p.radius_km) == pytest.approx((c.lat[0], c.lon[0], c.radius_km[0]))
    assert idx.layer_kind("parks") == "polygon" and idx.layer_kind(0) == "point"


def test_radius_columns_win_over_population(tmp_path):
    layer = point_layer([1.0, 2.0], [3.0, 4.0], radius_km=np.array([5.0, 0.0], dtype=np.float32))
    names = NameData.from_rows(
        [("A", "spots", 0, "park", 0.5, "official"), ("B", "spots", 1, "park", 0.5, "official")]
    )
    idx = open_pack(write_pack(tmp_path, "r", "2026.11", [layer], created=CREATED, names=names)).names
    assert idx.exact("a").radius_km[0] == pytest.approx(5.0)
    assert idx.exact("b").radius_km[0] == pytest.approx(nc.POINT_DEFAULT_RADIUS_KM)  # 0 is unknown


def test_candidates_take_and_empty(pack):
    c = pack.names.exact("Springfield")
    assert len(c.take(np.array([1]))) == 1
    assert c.take(np.array([1])).row.tolist() == [1]
    assert len(Candidates.empty()) == 0
    assert len(pack.names) == len(names_data(names_layers()))  # the kit's entries are all distinct


def test_duplicate_variants_collapse_to_the_best_name_kind(tmp_path):
    layer = point_layer([1.0], [2.0])
    names = NameData.from_rows(
        [
            ("Québec", "spots", 0, "locality", 0.5, "alias"),
            ("Quebec", "spots", 0, "locality", 0.5, "official"),
        ]
    )
    idx = open_pack(write_pack(tmp_path, "d", "2026.11", [layer], created=CREATED, names=names)).names
    c = idx.exact("quebec")
    assert len(c) == 1 and c.name_kind.tolist() == [nc.OFFICIAL]


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (("A", "nope", 0, "locality", 0.5, "official"), "layer"),
        (("A", "spots", 7, "locality", 0.5, "official"), "row"),
        (("A", "spots", 0, "village", 0.5, "official"), "kind"),
        (("A", "spots", 0, "locality", 1.5, "official"), "rank"),
        (("A", "spots", 0, "locality", 0.5, "nickname"), "name_kind"),
    ],
)
def test_bad_name_data_is_refused_before_writing(tmp_path, row, message):
    with pytest.raises(ValueError, match=message):
        write_pack(tmp_path, "bad", "2026.11", [point_layer([1.0], [2.0])], names=NameData.from_rows([row]))
    assert not (tmp_path / "bad-2026.11").exists()


def test_a_layer_may_not_be_called_names(tmp_path):
    with pytest.raises(ValueError, match="reserved"):
        write_pack(tmp_path, "bad", "2026.11", [point_layer([1.0], [2.0], name="names")])


def test_an_empty_index_answers_nothing(tmp_path):
    path = write_pack(
        tmp_path, "e", "2026.11", [point_layer([1.0], [2.0])], created=CREATED, names=NameData.from_rows([])
    )
    idx = open_pack(path).names
    assert len(idx) == 0
    for lookup in (idx.exact, idx.prefix, idx.fuzzy, idx.codes):
        assert len(lookup("anything")) == 0


def test_kit_cities_are_all_indexed(pack):
    for name, *_ in CITIES:
        assert len(pack.names.exact(name)) >= 1
