from pathlib import Path

import shapefile  # pyshp, to write one-off fixtures

from packbuild.sources import naturalearth
from placewise.model import Feature

DATA = Path(__file__).parent / "data"


def _col(layer, name):
    return list(layer.columns[name])


def test_countries_columns_and_fallbacks():
    layer = naturalearth.countries(DATA / "ne_countries.shp")
    assert layer.name == "countries" and layer.kind == "polygon"
    assert layer.sources == ("naturalearth",)
    assert len(layer.features) == 3
    assert _col(layer, "id") == ["iso:CA", "iso:IN", "ne:SOL"]  # "-99": no ISO code, NE's own code
    assert _col(layer, "name") == ["Canada", "India", "Somaliland"]  # empty NAME_EN falls back to NAME
    assert _col(layer, "iso2") == ["CA", "IN", ""]  # "-99" is stored as null, not as a code
    assert _col(layer, "iso3") == ["CAN", "IND", ""]
    assert _col(layer, "adm0_a3") == ["CAN", "IND", "SOL"]
    assert _col(layer, "sovereign") == ["Canada", "India", "Somaliland"]
    assert _col(layer, "type")[2] == "Sovereign country"
    assert _col(layer, "continent") == ["North America", "Asia", "Africa"]
    assert _col(layer, "population") == [37589262, 1366417754, 5096159]
    assert layer.types["population"] == "i8" and layer.types["iso2"] == "str"


def test_countries_keep_every_worldview_column():
    layer = naturalearth.countries(DATA / "ne_countries.shp")
    assert _col(layer, "adm0_a3_in") == ["CAN", "IND", "SOM"]  # India's view merges Somaliland
    assert _col(layer, "fclass_iso")[2] == "Unrecognized"
    for name in ("adm0_a3_us", "adm0_a3_in", "fclass_iso", "fclass_us", "fclass_in"):
        assert layer.types[name] == "str"
    assert naturalearth.worldviews(layer) == ["IN", "ISO", "US"]


def test_features_keep_their_geometry_in_source_order():
    layer = naturalearth.countries(DATA / "ne_countries.shp")
    toronto = [bool(f.contains(43.65, -79.38)) for f in layer.features]
    assert toronto == [True, False, False]
    assert layer.features[0].id == "iso:CA"


def test_a_shared_iso_code_goes_to_the_country_itself(tmp_path):
    # Natural Earth gives Australia and its dependencies the same ISO_A2_EH ("AU")
    base = tmp_path / "dup"
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON) as w:
        for field in ("ADM0_A3", "ISO_A2_EH", "ISO_A3_EH", "NAME", "NAME_EN"):
            w.field(field, "C", 40)
        for i, (a3, name) in enumerate([("CSI", "Coral Sea Is."), ("AUS", "Australia")]):
            w.poly([[(i, 0), (i, 1), (i + 1, 1), (i + 1, 0), (i, 0)]])
            w.record(a3, "AU", "AUS", name, name)
    layer = naturalearth.countries(base.with_suffix(".shp"))
    assert _col(layer, "id") == ["ne:CSI", "iso:AU"]
    assert _col(layer, "iso2") == ["AU", "AU"]  # the dependency still reports its ISO country


def test_admin1_columns_and_fallbacks():
    layer = naturalearth.admin1(DATA / "ne_admin1.shp")
    assert layer.name == "admin1" and layer.kind == "polygon" and layer.sources == ("naturalearth",)
    assert _col(layer, "id") == ["iso:CA-ON", "iso:IN-KA", "ne:SOL+00?", "ne:BIH-4801", "ne:BIH-4802"]
    assert _col(layer, "name") == ["Ontario", "Karnataka", "Somaliland", "Unsko-Sanski", "Posavski"]
    assert _col(layer, "country") == ["CA", "IN", "", "BA", "BA"]  # NE writes "-1" for none
    assert _col(layer, "code") == ["ON", "KA", "", "BIH", "BIH"]
    assert _col(layer, "adm0_a3") == ["CAN", "IND", "SOL", "BIH", "BIH"]
    assert _col(layer, "type_en")[:2] == ["Province", "State"]
    assert _col(layer, "name_alt")[1] == "Maisur|Mysore"
    assert _col(layer, "fclass_in")[2] == "Unrecognized"
    assert all(layer.types[c] == "str" for c in layer.columns)


def test_nul_padded_text_is_cleaned(monkeypatch):
    # Natural Earth's .dbf pads text fields with NUL bytes, which read_shapefile passes through
    real = naturalearth.read_shapefile

    def padded(path):
        pad = {str: lambda v: f"{v}\x00\x00"}
        return [
            Feature(f.outlines, {k: pad.get(type(v), lambda v: v)(v) for k, v in f.properties.items()})
            for f in real(path)
        ]

    monkeypatch.setattr(naturalearth, "read_shapefile", padded)
    layer = naturalearth.countries(DATA / "ne_countries.shp")
    assert _col(layer, "id") == ["iso:CA", "iso:IN", "ne:SOL"]
    assert _col(layer, "name")[0] == "Canada" and _col(layer, "adm0_a3_in")[2] == "SOM"
    admin1 = naturalearth.admin1(DATA / "ne_admin1.shp")
    assert _col(admin1, "id")[0] == "iso:CA-ON"


def test_placeholder_codes_without_a_tilde_are_not_iso(tmp_path):
    # "AI-X00" is Natural Earth's own placeholder; "AR-X" (Córdoba) is a real ISO 3166-2 code
    base = tmp_path / "a1"
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON) as w:
        for field in ("adm1_code", "iso_3166_2", "iso_a2", "name"):
            w.field(field, "C", 40)
        for i, (adm1, iso) in enumerate([("AIA-1", "AI-X00"), ("ARG-1", "AR-X"), ("CHN-1", "CN-XJ")]):
            w.poly([[(i, 0), (i, 1), (i + 1, 1), (i + 1, 0), (i, 0)]])
            w.record(adm1, iso, iso[:2], "x")
    layer = naturalearth.admin1(base.with_suffix(".shp"))
    assert _col(layer, "id") == ["ne:AIA-1", "iso:AR-X", "iso:CN-XJ"]
    assert _col(layer, "code") == ["", "X", "XJ"]
