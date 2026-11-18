"""packbuild.ind.layers: LGD-keyed polygon layers as unions of PIN area pieces. Synthetic squares
near Bengaluru and Delhi; LGD codes are real state codes, other codes made up."""

import numpy as np
import pytest

from packbuild.ind import layers
from packbuild.ind.layers import Piece
from packbuild.ind.lgd import Directory, Unit
from packbuild.ind.names import Names
from packbuild.layer import LayerData, write_pack
from placewise.model import Feature, Outline
from placewise.packs import open_pack

D = 0.01


def sq(col, row, x0=77.5, y0=12.9):
    """A clockwise (lon, lat) square, exact shared vertices with its neighbours."""
    x, y, x1, y1 = x0 + col * D, y0 + row * D, x0 + (col + 1) * D, y0 + (row + 1) * D
    return np.array([(x, y), (x, y1), (x1, y1), (x1, y)])


def directory():
    d = Directory()
    d.states = {
        "29": Unit("29", "Karnataka", "", "IN-KA", kind="state"),
        "37": Unit("37", "Ladakh", "", "IN-LA", kind="union territory"),
    }
    d.districts = {
        "572": Unit("572", "Bengaluru Urban", "29", "IN-KA", census2011="572"),
        "39": Unit("39", "Leh Ladakh", "37", "IN-LA", census2011="0"),
    }
    d.ulbs = {
        "900": Unit(
            "900",
            "Synthetic City Municipal Corporation",
            "29",
            "IN-KA",
            local_name="ಸಿಂಥೆಟಿಕ್",
            census2011="802000",
            kind="Municipal Corporation",
        ),
        "276400": Unit("276400", "North Delhi Municipal Corporation", "7", "IN-DL"),
    }
    return d


NAMES = Names(
    {
        ("district", "572"): {
            "name": "Bengaluru Urban",
            "former": [{"name": "Bangalore Urban"}],
            "aliases": ["Bangalore"],
        },
        ("ulb", "900"): {"name": "Synthetic City", "former": [{"name": "Old Synthetic"}]},
    },
    (
        {
            "id": "lgd:ulb:276402",
            "name": "Delhi",
            "official_name": "Municipal Corporation of Delhi",
            "state": "DL",
            "lgd": ["276400", "276401", "276402"],
            "aliases": ["MCD"],
        },
    ),
    (),
)


def test_display_name_drops_ulb_type_words():
    assert layers.display_name("Srinagar Municipal Corporation") == "Srinagar"
    assert layers.display_name("Municipal Committee Uri") == "Uri"
    assert layers.display_name("Nagar Panchayat") == "Nagar Panchayat"  # nothing left: kept
    assert layers.display_name("Hyderabad") == "Hyderabad"


def test_units_with_pieces_on_both_sides_get_an_india_view_row():
    pieces = [
        Piece(0, (sq(0, 0),), False),
        Piece(1, (sq(1, 0),), False),
        Piece(1, (sq(2, 0),), True),
        Piece(2, (sq(3, 0),), True),
    ]
    st = layers.states_layer(pieces, ["29", "29", "37"], directory(), NAMES, ("s",))
    c = st.columns
    assert c["id"] == ["lgd:state:29", "lgd:state:29#india-view", "lgd:state:37"]  # only view-only: no suffix
    assert c["india_view_only"] == [False, True, True]
    assert c["name"] == ["Karnataka", "Karnataka", "Ladakh"] and c["iso"] == ["IN-KA", "IN-KA", "IN-LA"]
    assert st.columns["area_km2"][0] == pytest.approx(2 * 1.205, rel=0.01)  # two cells dissolved


def test_districts_carry_lgd_and_curated_names():
    pieces = [Piece(0, (sq(0, 0),), False), Piece(1, (sq(1, 0),), False)]
    c = layers.districts_layer(pieces, ["572", "39"], directory(), NAMES, ("s",)).columns
    assert c["id"] == ["lgd:district:39", "lgd:district:572"]
    assert c["aliases"] == ["", "Bangalore Urban|Bangalore"] and c["census2011"] == ["", "572"]
    assert c["name"] == ["Leh Ladakh", "Bengaluru Urban"] and c["state_code"] == ["IN-LA", "IN-KA"]


def test_city_info_from_lgd_and_curated_cities():
    info = layers.city_info(["900", "276402", ""], directory(), NAMES, {"900": "572"})
    assert info["900"] == {
        "name": "Synthetic City",
        "official_name": "Synthetic City Municipal Corporation",
        "type": "Municipal Corporation",
        "state_code": "IN-KA",
        "district": "572",
        "census2011": "802000",
        "local_name": "ಸಿಂಥೆಟಿಕ್",
        "aliases": ["Old Synthetic", "Synthetic City Municipal Corporation"],
        "members": ["900"],
    }
    delhi = info["276402"]
    assert (delhi["name"], delhi["official_name"], delhi["state_code"]) == (
        "Delhi",
        "Municipal Corporation of Delhi",
        "IN-DL",
    )
    assert delhi["members"] == ["276400", "276401", "276402"] and delhi["aliases"] == ["MCD"]


def test_cities_smallest_first(tmp_path):
    pieces = [Piece(0, (sq(0, 0),), False), Piece(1, (sq(1, 0),), False), Piece(2, (sq(5, 5),), False)]
    info = layers.city_info(["900", "900", "276402"], directory(), NAMES, {})
    city = layers.cities_layer(pieces, ["900", "900", "276402"], info, ("s",))
    assert city.columns["id"] == ["lgd:ulb:276402", "lgd:ulb:900"]
    pack = open_pack(write_pack(tmp_path, "t", "2026.11", [city]))
    assert pack["cities"].value("name", int(pack["cities"].query(12.905, 77.515))) == "Synthetic City"


def test_pincodes_layer_keeps_whole_areas_and_splits_the_rest():
    whole = Feature(
        (
            Outline(
                (((12.9, 77.5), (12.91, 77.5), (12.91, 77.51), (12.9, 77.51)),),
            ),
        ),
        {},
        "pin:1",
    )
    pins = LayerData(
        "pincodes",
        "polygon",
        {"id": ["pin:194101", "pin:560001"], "name": ["Leh H.O", "GPO"]},
        ("a",),
        features=[whole, whole],
        types={"id": "str", "name": "str"},
    )
    pieces = [Piece(0, (sq(0, 0),), False), Piece(0, (sq(1, 0),), True), Piece(1, (sq(3, 0),), False)]
    out = layers.pincodes_layer(pins, pieces, {"city": ["", "lgd:ulb:900"]}, ("a", "b"))
    assert out.columns["id"] == ["pin:194101", "pin:194101#india-view", "pin:560001"]
    assert out.columns["india_view_only"] == [False, True, False]
    assert out.columns["city"] == ["", "", "lgd:ulb:900"] and out.columns["name"][1] == "Leh H.O"
    assert out.features[2] is whole and out.features[1].id == "pin:194101#india-view"
    assert out.sources == ("a", "b") and out.types["india_view_only"] == "bool"
