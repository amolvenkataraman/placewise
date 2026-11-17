"""packbuild.codab and packbuild.sources.ocha: COD-AB packages into country packs (synthetic
package from codab_fixtures; no network)."""

import struct

import numpy as np
import pytest
from codab_fixtures import ADM1, ADM2, CLAIM, write_level, write_package

from packbuild import claims, codab
from packbuild.sources import ocha, url
from placewise.model import Feature, Outline
from placewise.packs import open_pack

NAMES = [
    f"npl_admin{n}{em}.{e}" for n in (1, 2, 3) for em in ("", "_em") for e in ("shp", "shx", "dbf", "prj")
]


def test_members_prefer_the_edge_matched_layers():
    names = [n for n in NAMES if not (n.startswith("npl_admin2_em") or n.startswith("npl_admin3_em"))]
    names += ["npl_admin1_em.cpg", "npl_adminlines.shp"]
    assert ocha.level_stem(names, "npl", 1) == "npl_admin1_em"
    assert ocha.level_stem(names, "npl", 2) == "npl_admin2"
    assert ocha.members(names, "npl", 2) == [
        "npl_admin1_em.shp", "npl_admin1_em.shx", "npl_admin1_em.dbf", "npl_admin1_em.prj",
        "npl_admin1_em.cpg",
        "npl_admin2.shp", "npl_admin2.shx", "npl_admin2.dbf", "npl_admin2.prj",
    ]  # fmt: skip
    with pytest.raises(KeyError, match="npl_admin4"):
        ocha.level_stem(names, "npl", 4)


def test_rows_carry_ids_parents_and_types():
    props = {"adm2_name": "  Kaski ", "adm2_pcode": "NP0439", "adm1_pcode": "NP04", "valid_on": "2024-03-14"}
    assert ocha.row(props, 2) == {
        "id": "codab:NP0439", "name": "Kaski", "pcode": "NP0439", "parent": "codab:NP04", "type": "",
        "valid_on": "2024-03-14",
    }  # fmt: skip
    assert ocha.row({"adm1_name": "Ha Noi", "adm1_pcode": "VN01", "adm1_type_": "City"}, 1)["type"] == "City"
    assert ocha.row({"adm1_name": "Ha Noi", "adm1_pcode": "VN01"}, 1)["parent"] == ""
    with pytest.raises(ValueError, match="P-code"):
        ocha.row({"adm1_name": "Nowhere"}, 1)
    assert ocha.row({"adm1_pcode": "LK9"}, 1)["name"] == ""  # some units have no English name
    with pytest.raises(ValueError, match="adm1_pcode"):
        ocha.row({"adm2_name": "Orphan", "adm2_pcode": "NP9999"}, 2)


def test_overflowing_numbers_read_as_null(tmp_path):
    shp = write_level(tmp_path, "x_admin1", ADM1, 1)
    dbf = shp.with_suffix(".dbf")
    data = bytearray(dbf.read_bytes())
    at = data.index(b" 10.500000")  # the first record's center_lat
    data[at : at + 10] = b"*" * 10
    dbf.write_bytes(bytes(data))
    rows = list(ocha.read_dbf(dbf))
    assert rows[0]["center_lat"] is None and rows[1]["center_lat"] == 10.5
    assert rows[0]["adm1_name"] == "Province One"
    assert struct.unpack("<I", data[4:8])[0] == 2


def test_only_wgs84_files_are_read(tmp_path):
    shp = write_level(tmp_path, "x_admin1", ADM1, 1)
    shp.with_suffix(".prj").write_text('PROJCS["UTM",GEOGCS["WGS 84",DATUM["WGS_1984"]]]')
    with pytest.raises(ValueError, match="projected"):
        list(ocha.read_level(shp))


def test_local_plate_is_metres_on_the_ground():
    plate = codab.LocalPlate(60.0, 25.0)
    x, _ = plate.forward(np.array([25.0, 25.0 + 1 / 60]), np.array([60.0, 60.0]))
    assert x[1] - x[0] == pytest.approx(
        926.6, rel=1e-3
    )  # a minute of longitude at 60 N: half a nautical mile
    lon, lat = plate.inverse(*plate.forward(np.array([24.1, 26.3]), np.array([59.2, 61.0])))
    assert np.allclose(lon, [24.1, 26.3]) and np.allclose(lat, [59.2, 61.0])


def test_level_layer_simplifies_and_merges_records_of_one_unit(tmp_path):
    shp = write_level(tmp_path, "npl_admin1", ADM1, 1)
    layer = codab.level_layer("npl", 1, ocha.read_level(shp), tolerance_m=10)
    assert layer.name == "admin1" and layer.sources == ("ocha-cod-ab-npl",)
    assert layer.columns["id"] == ["codab:NP01", "codab:NP02"]
    assert layer.columns["parent"] == ["", ""]
    assert len(layer.features[0].outlines[0].rings[0]) == 4  # 80 collinear points down to the corners
    exact = codab.level_layer("npl", 1, ocha.read_level(shp), tolerance_m=0)
    assert len(exact.features[0].outlines[0].rings[0]) == 80


@pytest.fixture
def package(tmp_path):
    write_package(tmp_path, url(ocha.source_id("npl"), "shp"))
    return tmp_path


def claimant():
    ring = tuple((lat, lon) for lon, lat in CLAIM)
    return [Feature((Outline((ring,)),), {"ADM0_A3": "IND"})]


def test_build_layers_reads_every_level_with_parents(package, monkeypatch):
    monkeypatch.setitem(claims.SECTORS, "npl", ())
    layers = codab.build_layers("npl", package, claimant=claimant())
    assert [layer.name for layer in layers] == ["admin1", "admin2", "admin3"]
    admin1, admin2, admin3 = (layer.columns for layer in layers)
    assert admin1["name"] == ["Province One (em)", "Province Two (em)"]  # the _em file
    assert admin2["parent"] == ["codab:NP01", "codab:NP01", "codab:NP02"]
    assert admin3["id"] == [
        "codab:NP010101",
        "codab:NP010102",
        "codab:NP020101",
        "codab:NP010201",
        "codab:NP010202",
    ]
    echo = layers[2].features[4]
    assert len(echo.outlines) == 2  # the island record joined its unit
    assert layers[0].sources == ("ocha-cod-ab-npl",)


def test_claimed_ground_is_cut_out_of_every_level(package, monkeypatch):
    monkeypatch.setitem(claims.SECTORS, "npl", (("Test sector", (10.55, 170.35, 10.95, 170.65)),))
    layers = codab.build_layers("npl", package, claimant=claimant())
    lat, lon = np.meshgrid(np.linspace(10.0, 11.0, 101), np.linspace(170.0, 171.0, 101), indexing="ij")
    lat, lon = lat.ravel(), lon.ravel()
    in_claim = (lat > 10.6) & (lat < 10.9) & (lon > 170.4) & (lon < 170.6)
    for layer in layers:
        covered = np.zeros(len(lat), dtype=bool)
        for f in layer.features:
            for o in f.outlines:
                covered |= o.contains(lat, lon)
        assert not (covered & in_claim).any(), layer.name
        assert layer.sources == ("ocha-cod-ab-npl", "naturalearth")
    # outside the claim nothing changed: Bravo keeps its west half, Charlie its south
    bravo = layers[2].features[1]
    assert bravo.outlines[0].contains(10.75, 170.3) and not bravo.outlines[0].contains(10.75, 170.45)
    assert layers[2].features[2].outlines[0].contains(10.3, 170.55)


def test_a_unit_wholly_inside_a_claim_is_left_out(package, monkeypatch):
    monkeypatch.setitem(claims.SECTORS, "npl", (("Test sector", (10.0, 170.0, 11.0, 170.27)),))
    big = [
        Feature(
            (Outline((((10.4, 169.9), (11.1, 169.9), (11.1, 170.26), (10.4, 170.26)),)),), {"ADM0_A3": "IND"}
        )
    ]
    layers = codab.build_layers("npl", package, claimant=big)
    assert "codab:NP010101" not in layers[2].columns["id"]  # Alpha: 170.0-170.25, 10.5-11
    assert "codab:NP010102" in layers[2].columns["id"]


def test_leftover_finds_claimed_ground_still_inside():
    sector = (("S", (0.0, 0.0, 1.0, 1.0)),)
    ring = np.array([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])
    inside = Feature((Outline((((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),)),), {}, "codab:X")
    assert claims.leftover([inside], sector, [("S", ring)], step=0.1) == [("codab:X", "S", 36)]
    cut = claims.cut(inside, [("S", ring)])
    assert claims.leftover([cut], sector, [("S", ring)], step=0.1) == []
    assert len(cut.outlines) == 1 and len(cut.outlines[0].rings) == 2  # the claim became a hole


def test_build_writes_a_pack_named_by_alpha3(package, tmp_path, monkeypatch):
    monkeypatch.setitem(claims.SECTORS, "npl", ())
    path = codab.build("npl", package, tmp_path / "out", "2026.11")
    pack = open_pack(path, verify=True)
    assert pack.name == "npl" and [layer.name for layer in pack] == ["admin1", "admin2", "admin3"]
    assert pack["admin3"].column("name").tolist()[0] == "Alpha"
    assert pack.sources == ("ocha-cod-ab-npl",)
    with pytest.raises(ValueError, match="no COD-AB pack"):
        codab.build("pak", package, tmp_path / "out", "2026.11")


def test_every_configured_country_has_a_registry_entry():
    from placewise.constants.codab import COUNTRIES

    for iso3, config in COUNTRIES.items():
        source = ocha.source_id(iso3)
        assert url(source, "shp").endswith(f"{iso3}_admin_boundaries.shp.zip")
        from placewise.attribution import source as registered

        s = registered(source)
        assert s.licence == "CC-BY-3.0-IGO" and "OCHA" in s.credit
        assert s.used_in == tuple(f"{iso3}/admin{n}" for n in range(1, config.levels + 1))
    assert "pak" not in COUNTRIES  # Pakistan's COD-AB draws Pakistan's view of Jammu and Kashmir
    assert ADM2  # fixtures import check
