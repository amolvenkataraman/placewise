from packbuild.layer import LayerData


def test_layerdata_is_the_writers():
    layer = LayerData(
        "cities", "point", {"id": ["geonames:1"], "name": ["A"]}, ("geonames",), lat=[1.0], lon=[2.0]
    )
    assert layer.name == "cities" and layer.kind == "point"
    assert layer.features is None and layer.types == {} and layer.nulls == {} and layer.cell_deg == 1.0
