import math

import pytest
import us_fixtures as fx

from packbuild.sources.usa import census as uscensus
from placewise.io import read_shapefile

GOLDEN_GATE_PARK = (37.7694, -122.4862)
LAS_VEGAS_STRIP = (36.1147, -115.1728)
RENO = (39.5296, -119.8138)
YOSEMITE_VALLEY = (37.7456, -119.5936)


def _col(layer, name):
    return list(layer.columns[name])


def _containing(layer, point):
    return [fid for f, fid in zip(layer.features, layer.columns["id"], strict=True) if f.contains(*point)]


# --- NAD83 -------------------------------------------------------------------------------------


def test_placewise_itself_refuses_the_census_nad83_prj(tmp_path):
    # the reason the US loader opts in: read_shapefile is WGS84-only by default
    shp = fx.states(tmp_path)
    with pytest.raises(ValueError, match="not WGS84"):
        read_shapefile(shp)


def test_nad83_geographic_files_are_read_as_wgs84(tmp_path):
    shp = fx.states(tmp_path)
    features = uscensus.read_census_shapefile(shp)
    assert [f.properties["STUSPS"] for f in features] == ["NV", "CA", "GU"]
    # coordinates pass through unchanged: NAD83 and WGS84 differ by 1-2 m in the US
    assert features[2].outlines[0].rings[0][0] == (13.2, 144.6)
    assert (tmp_path / "cb_2025_us_state_500k.prj").exists()  # the input is left alone


def test_wgs84_and_unlabelled_files_are_read_too(tmp_path):
    fields = [("NAME", "C", 20)]
    rows = [(fx.box(0, 0, 1, 1), ("a",))]
    wgs = fx.write_shapefile(tmp_path / "wgs", fields, rows, prj=fx.WGS84_PRJ)
    bare = fx.write_shapefile(tmp_path / "bare", fields, rows, prj=None)
    assert uscensus.read_census_shapefile(wgs)[0].properties == {"NAME": "a"}
    assert uscensus.read_census_shapefile(bare)[0].properties == {"NAME": "a"}


@pytest.mark.parametrize(
    ("prj", "message"),
    [(fx.NAD27_PRJ, "NAD27|datum"), (fx.NAD83_ALBERS_PRJ, "projected")],
)
def test_other_datums_and_projections_are_refused(tmp_path, prj, message):
    shp = fx.write_shapefile(tmp_path / "x", [("NAME", "C", 20)], [(fx.box(0, 0, 1, 1), ("a",))], prj=prj)
    with pytest.raises(ValueError, match=message):
        uscensus.read_census_shapefile(shp)


# --- text inputs -------------------------------------------------------------------------------


def test_gazetteer_rows_by_geoid_with_padding_stripped(tmp_path):
    gaz = uscensus.read_gazetteer(fx.text_files(tmp_path)["gazetteer_place"])
    assert set(gaz) == {"0653000", "0667000", "3240000", "3254600", "3260600"}
    assert gaz["3240000"]["INTPTLONG"] == "-115.264037"  # trailing spaces gone
    assert gaz["3254600"]["FUNCSTAT"] == "S"


def test_gazetteer_reads_tab_separated_years_too(tmp_path):
    path = tmp_path / "2024_Gaz_zcta_national.txt"
    path.write_text(
        "GEOID\tALAND\tINTPTLAT\tINTPTLONG                 \n94117\t3301059\t37.770051\t-122.44428  \n"
    )
    assert uscensus.read_gazetteer(path) == {
        "94117": {"GEOID": "94117", "ALAND": "3301059", "INTPTLAT": "37.770051", "INTPTLONG": "-122.44428"}
    }


def test_population_keeps_incorporated_places_only_from_the_latest_year(tmp_path):
    pop = uscensus.read_population(fx.text_files(tmp_path)["population"])
    assert pop == {
        "0653000": 440838,
        "0667000": 826079,  # the SUMLEV 157 county-part row (1) is ignored
        "3240000": 679817,
        "3260600": 283621,
        "3525170": 10458,  # Española: the file is Latin-1
    }
    assert uscensus.population_year(fx.text_files(tmp_path)["population"]) == 2025


def test_xlsx_rows_follow_cell_references(tmp_path):
    path = fx.write_xlsx(tmp_path / "t.xlsx", [("a", "", "c"), (), ("x", 7)])
    assert uscensus.read_xlsx_rows(path) == [["a", "", "c"], [], ["x", "7"]]


def test_delineation_skips_titles_and_footnotes(tmp_path):
    rows = uscensus.read_delineation(fx.delineation(tmp_path))
    assert len(rows) == len(fx.DELINEATION_ROWS)
    sf = next(r for r in rows if r["county"] == "06075")
    assert sf == {
        "cbsa": "41860",
        "csa": "488",
        "metdiv": "41884",
        "type": "metro",
        "county": "06075",
        "central": True,
    }
    storey = next(r for r in rows if r["county"] == "32029")
    assert storey["central"] is False
    assert next(r for r in rows if r["cbsa"] == "21220")["type"] == "micro"


# --- layers ------------------------------------------------------------------------------------


def test_states_use_iso_ids_like_world_admin1(tmp_path):
    layer = uscensus.states(fx.states(tmp_path))
    assert layer.name == "states" and layer.kind == "polygon" and layer.sources == ("uscensus",)
    assert _col(layer, "id") == ["iso:US-CA", "iso:US-NV", "iso:US-GU"]  # sorted by FIPS code
    assert _col(layer, "name") == ["California", "Nevada", "Guam"]
    assert _col(layer, "usps") == ["CA", "NV", "GU"]
    assert _col(layer, "statefp") == ["06", "32", "66"]
    assert _containing(layer, YOSEMITE_VALLEY) == ["iso:US-CA"]
    assert _containing(layer, RENO) == ["iso:US-NV"]
    assert _containing(layer, LAS_VEGAS_STRIP) == ["iso:US-NV"]
    assert set(layer.types) == set(layer.columns)


def test_counties_names_with_lsad_and_metro_membership(tmp_path):
    layer = uscensus.counties(fx.counties(tmp_path), uscensus.read_delineation(fx.delineation(tmp_path)))
    assert layer.name == "counties" and layer.kind == "polygon"
    assert _col(layer, "id") == [
        "census:06001",
        "census:06043",
        "census:06075",
        "census:32003",
        "census:32031",
    ]
    assert _col(layer, "name")[2] == "San Francisco County"
    assert _col(layer, "basename")[2] == "San Francisco"
    assert _col(layer, "lsad") == ["County"] * 5
    assert _col(layer, "state") == ["CA", "CA", "CA", "NV", "NV"]
    assert _col(layer, "statefp")[3] == "32" and _col(layer, "countyfp")[3] == "003"
    assert _col(layer, "cbsa") == ["41860", "", "41860", "29820", "39900"]  # Mariposa is in no CBSA
    assert _col(layer, "csa") == ["488", "", "488", "332", "456"]
    assert _col(layer, "central") == ["central", "", "central", "central", "central"]
    assert _containing(layer, GOLDEN_GATE_PARK) == ["census:06075"]
    assert _containing(layer, YOSEMITE_VALLEY) == ["census:06043"]


def test_counties_without_a_delineation_have_empty_membership(tmp_path):
    layer = uscensus.counties(fx.counties(tmp_path))
    assert set(_col(layer, "cbsa")) == {""} and set(_col(layer, "csa")) == {""}


def test_places_columns_joins_and_order(tmp_path):
    text = fx.text_files(tmp_path)
    layer = uscensus.places(
        fx.places(tmp_path),
        uscensus.read_gazetteer(text["gazetteer_place"]),
        uscensus.read_population(text["population"]),
    )
    assert layer.name == "places" and layer.kind == "polygon" and layer.sources == ("uscensus",)
    # incorporated places first (they win where a CDP overlaps), then CDPs; by GEOID within each
    ids = _col(layer, "id")
    incorporated = ["census:0653000", "census:0667000", "census:3240000", "census:3260600", "census:6633400"]
    assert ids == [*incorporated, "census:3254600"]
    row = {name: values[ids.index("census:3254600")] for name, values in layer.columns.items()}
    assert row["name"] == "Paradise" and row["full_name"] == "Paradise CDP"
    assert row["lsad"] == "CDP" and row["lsad_code"] == "57" and row["class"] == "cdp"
    assert row["funcstat"] == "S" and row["state"] == "NV" and row["statefp"] == "32"
    assert row["population"] is None  # SUB-EST covers incorporated places only
    assert row["aland"] == 109826233
    assert (row["intpt_lat"], row["intpt_lon"]) == (36.087148, -115.135519)
    sf = ids.index("census:0667000")
    assert _col(layer, "population")[sf] == 826079
    assert _col(layer, "class")[sf] == "incorporated" and _col(layer, "lsad")[sf] == "city"
    guam = ids.index("census:6633400")
    assert _col(layer, "name")[guam] == "Hagåtña" and _col(layer, "lsad")[guam] == "village"
    assert _col(layer, "funcstat")[guam] == ""  # not in the gazetteer
    assert math.isnan(_col(layer, "intpt_lat")[guam]) and _col(layer, "population")[guam] is None
    assert layer.types["population"] == "i8" and layer.nulls == {"population": uscensus.POPULATION_NULL}
    assert layer.types["intpt_lat"] == "f8" and layer.types["aland"] == "i8"
    assert set(layer.types) == set(layer.columns)
    assert _containing(layer, LAS_VEGAS_STRIP) == ["census:3254600"]  # the Strip is not in Las Vegas
    assert _containing(layer, GOLDEN_GATE_PARK) == ["census:0667000"]
    assert _containing(layer, RENO) == ["census:3260600"]
    assert _containing(layer, YOSEMITE_VALLEY) == []
    assert all(f.id == i for f, i in zip(layer.features, ids, strict=True))


def test_places_without_joins(tmp_path):
    layer = uscensus.places(fx.places(tmp_path))
    assert set(_col(layer, "funcstat")) == {""}
    assert _col(layer, "population") == [None] * 6
    assert _col(layer, "class").count("cdp") == 1  # class comes from the LSAD code, not the gazetteer


def test_cbsa_type_csa_and_member_counties(tmp_path):
    layer = uscensus.cbsa(fx.cbsa(tmp_path), uscensus.read_delineation(fx.delineation(tmp_path)))
    assert layer.name == "cbsa" and layer.kind == "polygon"
    assert _col(layer, "id") == [
        "census:cbsa:21220",
        "census:cbsa:29820",
        "census:cbsa:39900",
        "census:cbsa:41860",
    ]
    assert _col(layer, "name")[3] == "San Francisco-Oakland-Fremont, CA Metro Area"
    assert _col(layer, "title")[3] == "San Francisco-Oakland-Fremont, CA"
    assert _col(layer, "code") == ["21220", "29820", "39900", "41860"]
    assert _col(layer, "type") == ["micro", "metro", "metro", "metro"]
    assert _col(layer, "csa") == ["", "332", "456", "488"]
    assert _col(layer, "counties") == ["32007", "32003", "32029,32031", "06001,06075"]
    assert _containing(layer, GOLDEN_GATE_PARK) == ["census:cbsa:41860"]


def test_csa_member_cbsas_and_counties(tmp_path):
    layer = uscensus.csa(fx.csa(tmp_path), uscensus.read_delineation(fx.delineation(tmp_path)))
    assert layer.name == "csa" and layer.kind == "polygon"
    assert _col(layer, "id") == ["census:csa:332", "census:csa:456", "census:csa:488"]
    assert _col(layer, "name")[2] == "San Jose-San Francisco-Oakland, CA CSA"
    assert _col(layer, "title")[2] == "San Jose-San Francisco-Oakland, CA"
    assert _col(layer, "cbsas") == ["29820", "39900", "41860,41940"]
    assert _col(layer, "counties")[2] == "06001,06075,06085"
    assert _containing(layer, GOLDEN_GATE_PARK) == ["census:csa:488"]


def test_zcta_polygons_with_internal_points(tmp_path):
    gaz = uscensus.read_gazetteer(fx.text_files(tmp_path)["gazetteer_zcta"])
    layer = uscensus.zcta(fx.zcta(tmp_path), gaz)
    assert layer.name == "zcta" and layer.kind == "polygon"
    assert _col(layer, "id") == ["census:zcta:89109", "census:zcta:94117", "census:zcta:95389"]
    assert _col(layer, "name") == ["89109", "94117", "95389"]
    assert _col(layer, "aland") == [10683404, 3301059, 778855970]
    assert _col(layer, "intpt_lat")[1] == 37.770051
    assert _containing(layer, LAS_VEGAS_STRIP) == ["census:zcta:89109"]


def test_zcta_points_from_the_gazetteer(tmp_path):
    layer = uscensus.zcta_points(uscensus.read_gazetteer(fx.text_files(tmp_path)["gazetteer_zcta"]))
    assert layer.name == "zcta" and layer.kind == "point"
    assert _col(layer, "id") == ["census:zcta:89109", "census:zcta:94117", "census:zcta:95389"]
    assert list(layer.lat) == [36.131622, 37.770051, 37.784127]
    assert list(layer.lon) == [-115.169932, -122.44428, -119.428263]
    assert set(layer.types) == set(layer.columns)
