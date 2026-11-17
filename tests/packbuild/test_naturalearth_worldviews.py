"""The `worldviews` layer: Natural Earth's disputed areas with every view's admin-0 unit."""

from pathlib import Path

import shapefile  # pyshp, to write one-off fixtures

from packbuild.sources import naturalearth

DATA = Path(__file__).parent / "data"


def _col(layer, name):
    return list(layer.columns[name])


def test_disputed_areas_layer_columns():
    layer = naturalearth.disputed_areas(DATA / "ne_disputed_areas.shp")
    assert layer.name == "worldviews" and layer.kind == "polygon"
    assert layer.sources == ("naturalearth",)
    assert _col(layer, "id") == ["ne:1000000001", "ne:1000000002"]
    assert _col(layer, "name") == ["Somaliland", "Test Island"]  # the byte-order mark is gone
    assert _col(layer, "adm0_a3") == ["SOL", "CAN"]
    assert _col(layer, "type") == ["Disputed", "Indeterminate"]
    assert _col(layer, "note")[0] == "Self admin.; Claimed by Somalia"
    # every view's unit, verbatim ("-99" is Natural Earth's "no value"); FCLASS columns are dropped
    assert _col(layer, "adm0_a3_in") == ["SOM", "CAN"]
    assert _col(layer, "adm0_a3_us") == ["SOM", "-99"]
    assert not any(name.startswith("fclass") for name in layer.columns)
    assert set(layer.types) == set(layer.columns) and set(layer.types.values()) == {"str"}
    assert [f.id for f in layer.features] == _col(layer, "id")
    assert layer.features[0].contains(9.5, 44.5)


def test_disputed_area_spellings_are_corrected(tmp_path):
    base = tmp_path / "areas"
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON) as w:
        for field in ("ADM0_A3", "BRK_NAME", "NAME"):
            w.field(field, "C", 40)
        w.field("NE_ID", "N", 10, 0)
        w.poly([[(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]])
        w.record("XXX", "Ilemi Triange", "Somewhere", 7)
    layer = naturalearth.disputed_areas(base.with_suffix(".shp"))
    assert _col(layer, "name") == ["Ilemi Triangle"]
    assert _col(layer, "id") == ["ne:7"]
