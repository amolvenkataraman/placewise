import pytest
from india_fixtures import (
    NSF_LCC_PRJ,
    NWDP_DISTRICTS,
    NWDP_STATES,
    write_nwdp_geojson,
    write_nwdp_shapefile,
)

from packbuild.sources.ind import nwdp


def _col(layer, name):
    return list(layer.columns[name])


def test_states_ids_are_iso_codes_with_lgd_codes_kept(tmp_path):
    layer = nwdp.states(write_nwdp_geojson(tmp_path / "state_NWIC.geojson", NWDP_STATES))
    assert layer.name == "states" and layer.kind == "polygon" and layer.sources == ("nwdp-soi-boundaries",)
    assert _col(layer, "id") == ["iso:IN-KA", "iso:IN-MH", "iso:IN-TS", "iso:IN-DL", "iso:IN-LA", "iso:IN-AR"]
    assert _col(layer, "iso") == ["IN-KA", "IN-MH", "IN-TS", "IN-DL", "IN-LA", "IN-AR"]
    assert _col(layer, "lgd") == ["29", "27", "36", "07", "37", "12"]
    # names from the ISO list; the portal's own spelling is kept beside it
    assert _col(layer, "name")[-1] == "Arunachal Pradesh"
    assert _col(layer, "source_name")[-1] == "Arunanchal Pradesh"
    assert layer.features[0].contains(12.9756, 77.6060)
    assert all(layer.types[c] == "str" for c in layer.columns)


def test_districts_ids_are_lgd_codes(tmp_path):
    layer = nwdp.districts(write_nwdp_geojson(tmp_path / "district_nwic.geojson", NWDP_DISTRICTS))
    assert layer.name == "districts" and layer.kind == "polygon"
    assert _col(layer, "id") == ["lgd:572", "lgd:482", "lgd:717"]
    assert _col(layer, "name") == ["Bengaluru Urban", "Mumbai", "Kamjong"]
    assert _col(layer, "state_code") == ["IN-KA", "IN-MH", "IN-MN"]
    assert _col(layer, "state_lgd") == ["29", "27", "14"]
    assert _col(layer, "state") == ["Karnataka", "Maharashtra", "Manipur"]
    assert layer.features[1].contains(18.9220, 72.8347)


def test_shapefiles_in_wgs84_read_the_same(tmp_path):
    shp = write_nwdp_shapefile(tmp_path / "state_NWIC", NWDP_STATES)
    geojson = write_nwdp_geojson(tmp_path / "state_NWIC.geojson", NWDP_STATES)
    assert nwdp.states(shp).columns == nwdp.states(geojson).columns


def test_the_portals_projected_files_are_refused(tmp_path):
    # the portal's GeoJSON and shapefile are in WGS 84 / India NSF LCC (EPSG:7755), metres
    geojson = write_nwdp_geojson(tmp_path / "state.geojson", NWDP_STATES, crs="urn:ogc:def:crs:EPSG::7755")
    with pytest.raises(ValueError, match="EPSG::7755"):
        nwdp.states(geojson)
    shp = write_nwdp_shapefile(tmp_path / "state_NWIC", NWDP_STATES, prj=NSF_LCC_PRJ)
    with pytest.raises(ValueError, match="projected"):
        nwdp.states(shp)


def test_an_unknown_state_code_is_an_error(tmp_path):
    props, box = NWDP_STATES[0]
    path = write_nwdp_geojson(tmp_path / "s.geojson", [({**props, "state": "ZZ"}, box)])
    with pytest.raises(ValueError, match="ZZ"):
        nwdp.states(path)
