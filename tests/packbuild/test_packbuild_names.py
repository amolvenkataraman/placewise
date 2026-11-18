import numpy as np
import pytest

from packbuild import name_specs
from packbuild.names import LayerNames, Rank, Term, build, for_pack, rank_of
from placewise.constants import names as nc
from placewise.model import Feature, Outline
from placewise.packs import LayerData, open_pack, write_pack


def _cities():
    return LayerData(
        name="cities",
        kind="point",
        columns={
            "id": ["synthetic:1", "synthetic:2", "synthetic:3"],
            "name": ["Mumbai", "Toronto", "Smallville"],
            "asciiname": ["Mumbai", "Toronto", "Smallville"],
            "aliases": ["Bombay|BOM", "", None],
            "population": np.array([12_000_000, 2_800_000, -1]),
        },
        sources=("synthetic",),
        lat=np.array([19.0, 43.6, 40.0]),
        lon=np.array([72.8, -79.4, -90.0]),
    )


def _areas():
    ring = ((0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0))
    return LayerData(
        name="areas",
        kind="polygon",
        columns={
            "id": ["iso:XX-AA"],
            "name": ["Alpha Province"],
            "code": ["AA"],
            "country": ["XX"],
            "iso3": ["-99"],
            "intpt_lat": [1.0],
            "intpt_lon": [1.5],
        },
        sources=("synthetic",),
        features=[Feature(outlines=(Outline((ring,)),))],
    )


CITY_SPEC = LayerNames(
    "cities",
    "locality",
    names=("name", "asciiname"),
    aliases=("aliases",),
    rank=Rank(base=0.1, span=0.85, column="population", lo=2.5, hi=7.3),
)


def _rows(data):
    return list(zip(data.text, data.layer, data.row, data.kind, data.name_kind, strict=True))


def test_names_aliases_and_abbreviations_become_entries():
    data = build([_cities()], [CITY_SPEC])
    rows = _rows(data)
    assert ("Mumbai", "cities", 0, "locality", "official") in rows
    assert ("Bombay", "cities", 0, "locality", "alias") in rows
    assert ("BOM", "cities", 0, "locality", "abbreviation") in rows
    assert sum(r[0] == "Toronto" for r in rows) == 2  # name and asciiname; the writer dedupes
    assert all(0 <= r <= 1 for r in data.rank)


def test_rank_follows_population_and_nulls_get_the_base():
    rank = rank_of(CITY_SPEC.rank, _cities().columns, 3)
    assert rank[0] > rank[1] > rank[2]
    assert rank[2] == pytest.approx(0.1)
    assert rank[0] == pytest.approx(min(0.1 + 0.85 * (np.log10(12e6 + 1) - 2.5) / 4.8, 1))


def test_rank_terms_invert_and_values():
    columns = {"tier": [1, 4], "type": ["large", "small"]}
    rank = Rank(
        base=0.1,
        terms=(
            Term("tier", 0.4, lo=1, hi=4, scale="invert"),
            Term("type", 0.2, scale="values", values={"large": 1}),
        ),
    )
    assert rank_of(rank, columns, 2).tolist() == pytest.approx([0.7, 0.1])


def test_codes_templates_id_prefixes_and_label_points():
    spec = LayerNames(
        "areas",
        "admin1",
        codes=("code", "{country}-{code}", "iso3"),
        id_codes=("iso:",),
        point=("intpt_lat", "intpt_lon"),
    )
    data = build([_areas()], [spec])
    codes = sorted(t for t, k in zip(data.text, data.name_kind, strict=True) if k == "code")
    assert codes == ["AA", "XX-AA", "XX-AA"]  # "-99" is Natural Earth's "none"
    assert data.points["areas"][0].tolist() == [1.0] and data.points["areas"][1].tolist() == [1.5]


def test_suffixes_are_stripped_from_names():
    layer = _cities()
    layer.columns["name"] = ["Koramangala S.O", "Fort B.O", "S.O"]
    data = build([layer], [LayerNames("cities", "sublocality", strip_suffixes=(" S.O", " B.O"))])
    assert list(data.text) == ["Koramangala", "Fort", "S.O"]


def test_missing_columns_and_layers_are_skipped():
    spec = LayerNames("cities", "locality", aliases=("aliases", "nicknames"), codes=("iata", "{x}-{y}"))
    assert len(build([_cities()], [spec, LayerNames("nowhere", "park")]).text) == 5
    assert len(build([_areas()], [CITY_SPEC]).text) == 0


def test_built_names_write_and_answer(tmp_path):
    layers = [_cities(), _areas()]
    data = build(layers, [CITY_SPEC, LayerNames("areas", "admin1", id_codes=("iso:",))])
    idx = open_pack(write_pack(tmp_path, "t", "2026.11", layers, names=data)).names
    c = idx.exact("bombay")
    assert c.row.tolist() == [0] and c.name_kind.tolist() == [nc.ALIAS]
    assert idx.codes("XX-AA").row.tolist() == [0]


def test_for_pack_knows_every_builder():
    assert {"world", "usa", "can", "ind", "world-water", "parks", "lka", "are"} <= set(name_specs.SPECS)
    assert len(for_pack("world", [_cities()]).text) > 0
    with pytest.raises(KeyError, match="no name index spec"):
        for_pack("atlantis", [])


def test_spec_kinds_are_place_kinds():
    for specs in name_specs.SPECS.values():
        for spec in specs:
            assert spec.kind in nc.PLACE_KINDS, spec.layer


def test_codab_levels_follow_the_country_table():
    kinds = [spec.kind for spec in name_specs.SPECS["lka"]]
    assert kinds == ["admin1", "admin2", "admin2", "sublocality"]
    assert [spec.kind for spec in name_specs.SPECS["npl"]] == ["admin1", "admin2", "locality"]
    assert [spec.layer for spec in name_specs.SPECS["are"]] == ["admin1"]


def test_a_kind_column_sets_each_row_s_kind():
    layer = LayerData(
        name="notable",
        kind="point",
        columns={"id": ["w:1", "w:2", "w:3"], "name": ["Tower", "Museum", "Odd"],
                 "kind": ["landmark", "museum", "unheard-of"], "aliases": ["T", "", ""]},
        sources=("synthetic",),
        lat=np.zeros(3),
        lon=np.zeros(3),
    )  # fmt: skip
    spec = LayerNames("notable", "landmark", aliases=("aliases",), kind_column="kind",
                      kind_values={"landmark": "landmark", "museum": "building"})  # fmt: skip
    data = build([layer], [spec])
    assert list(zip(data.text, data.kind, strict=True)) == [
        ("Tower", "landmark"), ("Museum", "building"), ("Odd", "landmark"), ("T", "landmark")
    ]  # fmt: skip


def test_world_notable_spec():
    from placewise.constants import notable

    (spec,) = name_specs.SPECS["world-notable"]
    assert spec.layer == notable.LAYER and spec.kind_values == notable.KINDS
    assert "aliases" in spec.aliases and set(spec.codes) == {"iata", "icao", "station_code"}
    assert spec.id_codes == ("wikidata:",)
    fame = {"fame": np.array([0.0, 0.5, 0.75, 1.0])}
    assert rank_of(spec.rank, fame, 4).tolist() == pytest.approx([0.15, 0.15, 0.5, 0.85])


def test_rows_a_skip_column_flags_are_not_indexed():
    # the India pack repeats a unit as its `#india-view` piece: one entry per unit is enough
    layer = LayerData(
        "states", "point",
        {"id": ["lgd:state:37", "lgd:state:37#india-view"], "name": ["Ladakh", "Ladakh"],
         "aliases": ["", ""], "india_view_only": [False, True]},
        ("synthetic",), lat=np.array([34.0, 35.0]), lon=np.array([77.0, 76.0]),
    )  # fmt: skip
    data = build([layer], [LayerNames("states", "admin1", skip="india_view_only")])
    assert data.text == ["Ladakh"] and data.row == [0]


def test_india_specs_index_the_lgd_layers():
    layers = {spec.layer: spec for spec in name_specs.SPECS["ind"]}
    assert {"states", "districts", "cities", "neighbourhoods"} <= set(layers)
    assert layers["states"].kind == "admin1" and layers["districts"].kind == "admin2"
    assert layers["cities"].kind == "locality" and layers["neighbourhoods"].kind == "sublocality"
    assert all(layers[k].skip == "india_view_only" for k in ("states", "districts", "cities"))
