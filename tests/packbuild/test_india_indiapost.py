import json
import logging

import numpy as np
import pytest
from india_fixtures import (
    DIRECTORY_HEADER,
    directory_rows,
    placement_features,
    placement_rows,
    write_boundaries,
    write_directory,
    write_placement_directory,
)

from packbuild.sources.ind import indiapost


def _col(layer, name):
    return list(layer.columns[name])


@pytest.fixture
def files(tmp_path):
    return write_boundaries(tmp_path / "boundaries.geojson"), write_directory(tmp_path / "pincode.csv")


# --- office coordinates against their own PIN area -------------------------------------------------


@pytest.fixture
def placed(tmp_path):
    boundaries = write_boundaries(tmp_path / "b.geojson", placement_features())
    offices = indiapost.post_offices(write_placement_directory(tmp_path / "d.csv"))
    return offices, indiapost.pincodes(boundaries)


def test_each_office_is_placed_against_its_own_pin_area(placed):
    offices, pincodes = placed
    assert _col(offices, "name") == [row[0] for row in placement_rows()]  # all have usable coordinates
    where = indiapost.office_placement(offices, pincodes)
    assert list(where) == [row[-1] for row in placement_rows()]


def test_the_buffer_is_two_km_and_can_be_changed(placed):
    assert indiapost.OFFICE_BUFFER_KM == 2.0
    offices, pincodes = placed
    edge = _col(offices, "name").index("Edge S.O")  # 1.6 km outside its area
    assert indiapost.office_placement(offices, pincodes, buffer_km=1.0)[edge] == "outside"
    assert indiapost.office_placement(offices, pincodes, buffer_km=0)[edge] == "outside"


def test_only_offices_in_or_near_their_own_area_keep_their_coordinates(placed, caplog):
    offices, pincodes = placed
    with caplog.at_level(logging.INFO):
        kept, counts = indiapost.keep_placed_offices(offices, pincodes)
    expected = [row for row in placement_rows() if row[-1] in ("inside", "near")]
    assert _col(kept, "name") == [row[0] for row in expected]
    np.testing.assert_array_equal(kept.lat, [row[2] for row in expected])
    np.testing.assert_array_equal(kept.lon, [row[3] for row in expected])
    assert set(kept.columns) == set(offices.columns) and kept.types == offices.types
    assert all(len(c) == len(expected) for c in kept.columns.values())
    assert (kept.name, kept.kind, kept.sources) == (offices.name, offices.kind, offices.sources)
    assert counts == {"inside": 4, "near": 1, "elsewhere": 1, "outside": 2, "no_area": 1}
    assert "kept 5 of 9" in caplog.text and "4 in their own PIN area (44.4%)" in caplog.text
    assert "2 in no PIN area" in caplog.text and "1 whose PIN code has no area" in caplog.text


def test_ids_stay_as_the_directory_gave_them(placed):
    offices, pincodes = placed
    kept, _ = indiapost.keep_placed_offices(offices, pincodes)
    assert set(_col(kept, "id")) <= set(_col(offices, "id"))
    assert "indiapost:560001:Bengaluru G.P.O." in _col(kept, "id")


def test_no_offices_is_not_an_error(tmp_path, placed):
    _, pincodes = placed
    empty = indiapost.post_offices(write_directory(tmp_path / "empty.csv", rows=[]))
    kept, counts = indiapost.keep_placed_offices(empty, pincodes)
    assert len(kept.columns["id"]) == 0 and sum(counts.values()) == 0


def test_pincode_ids_names_and_postal_hierarchy(files):
    layer = indiapost.pincodes(*files)
    assert layer.name == "pincodes" and layer.kind == "polygon"
    assert layer.sources == ("indiapost-pincode-boundary", "indiapost-pincode-directory")
    # the feature without a PIN code is dropped; the second 560001 polygon joins the first
    assert _col(layer, "id") == ["pin:560001", "pin:400001", "pin:500002", "pin:110001", "pin:194101"]
    assert _col(layer, "pincode") == ["560001", "400001", "500002", "110001", "194101"]
    assert _col(layer, "name")[:2] == ["Bengaluru G.P.O.", "Mumbai G.P.O."]
    assert _col(layer, "division")[0] == "BENGALURU GPO"  # trailing spaces trimmed
    assert _col(layer, "region") == ["Bengaluru HQ", "Mumbai HQ", "Hyderabad HQ", "", ""]
    assert _col(layer, "circle") == ["Karnataka", "Maharashtra", "Telangana", "Delhi", "Jammu & Kashmir"]
    assert all(layer.types[c] == "str" for c in layer.columns)
    assert set(layer.columns) == set(layer.types)


def test_pincode_geometry_is_merged_and_kept_in_lat_lon(files):
    layer = indiapost.pincodes(*files)
    bengaluru, mumbai = layer.features[0], layer.features[1]
    assert len(bengaluru.outlines) == 2 and len(mumbai.outlines) == 2
    assert bengaluru.id == "pin:560001"
    assert bengaluru.contains(12.9756, 77.6060)  # MG Road
    assert bengaluru.contains(13.015, 77.585)  # the merged second polygon
    assert not bengaluru.contains(18.9220, 72.8347)
    assert mumbai.contains(18.9220, 72.8347)  # Gateway of India


def test_district_and_state_are_joined_from_the_directory(files):
    layer = indiapost.pincodes(*files)
    # 560001 has two offices in Bengaluru Urban and one in Bengaluru Rural: the majority wins
    assert _col(layer, "district") == ["BENGALURU URBAN", "MUMBAI", "HYDERABAD", "NEW DELHI", ""]
    assert _col(layer, "state") == ["KARNATAKA", "MAHARASHTRA", "TELANGANA", "DELHI", ""]
    assert _col(layer, "state_code") == ["IN-KA", "IN-MH", "IN-TS", "IN-DL", ""]


def test_pincodes_without_a_directory_carry_no_district(files):
    layer = indiapost.pincodes(files[0])
    assert layer.sources == ("indiapost-pincode-boundary",)
    assert set(_col(layer, "district")) == {""} and set(_col(layer, "state_code")) == {""}


def test_district_ties_go_to_the_head_office_then_alphabetically():
    rows = [
        {"pincode": "123456", "office_type": "BO", "district": "B", "state": "S"},
        {"pincode": "123456", "office_type": "HO", "district": "C", "state": "S"},
        {"pincode": "654321", "office_type": "BO", "district": "Z", "state": "S"},
        {"pincode": "654321", "office_type": "BO", "district": "Y", "state": "S"},
    ]
    assert indiapost.pincode_districts(rows) == {"123456": ("C", "S"), "654321": ("Y", "S")}


def test_a_projected_or_foreign_crs_is_refused(tmp_path):
    path = write_boundaries(tmp_path / "b.geojson")
    data = json.loads(path.read_text())
    data["crs"]["properties"]["name"] = "urn:ogc:def:crs:EPSG::7755"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="EPSG::7755"):
        indiapost.pincodes(path)


def test_post_offices_keep_valid_coordinates_only(files, caplog):
    with caplog.at_level(logging.INFO):
        layer = indiapost.post_offices(files[1])
    assert layer.name == "post_offices" and layer.kind == "point"
    assert layer.sources == ("indiapost-pincode-directory",)
    names = _col(layer, "name")
    # NA, the 1/1 placeholder and a value with a trailing "-" are dropped; the duplicate row is kept once
    assert "Town Hall S.O" not in names and "Bazargate S.O" not in names and "Stock Exchange S.O" not in names
    assert names.count("Charminar S.O") == 1
    assert len(names) == 9
    assert "3 offices without usable coordinates" in caplog.text


def test_post_office_ids_columns_and_types(files):
    layer = indiapost.post_offices(files[1])
    ids = _col(layer, "id")
    assert ids[0] == "indiapost:560001:Bengaluru G.P.O."
    assert len(set(ids)) == len(ids)
    # the same office name twice under one PIN code: the second gets a suffix
    assert "indiapost:110001:Parliament House S.O" in ids and "indiapost:110001:Parliament House S.O#2" in ids
    i = ids.index("indiapost:560001:Bengaluru G.P.O.")
    assert (layer.lat[i], layer.lon[i]) == (12.9839, 77.5929)
    assert _col(layer, "office_type")[i] == "HO" and _col(layer, "delivery")[i] is True
    assert _col(layer, "delivery")[1] is False  # Vidhana Soudha S.O: "Non Delivery"
    assert _col(layer, "district")[i] == "BENGALURU URBAN" and _col(layer, "state_code")[i] == "IN-KA"
    assert _col(layer, "circle")[i] == "Karnataka Circle"
    j = _col(layer, "name").index("Silvassa S.O")
    assert _col(layer, "state_code")[j] == "IN-DH"  # "THE DADRA AND NAGAR HAVELI AND DAMAN AND DIU"
    assert layer.types["delivery"] == "bool" and layer.types["pincode"] == "str"
    assert set(layer.columns) == set(layer.types)


def test_api_export_with_lower_case_headers_reads_the_same(tmp_path, files):
    lower = write_directory(tmp_path / "api.csv", header=[h.lower() for h in DIRECTORY_HEADER])
    assert _col(indiapost.post_offices(lower), "id") == _col(indiapost.post_offices(files[1]), "id")


def test_a_directory_missing_a_column_is_an_error(tmp_path):
    header = [h for h in DIRECTORY_HEADER if h != "District"]
    rows = [
        [v for h, v in zip(DIRECTORY_HEADER, r, strict=True) if h != "District"] for r in directory_rows()
    ]
    path = write_directory(tmp_path / "bad.csv", rows=rows, header=header)
    with pytest.raises(ValueError, match="District"):
        indiapost.post_offices(path)


def test_state_codes_cover_every_state_and_union_territory():
    assert len(set(indiapost.STATE_CODES.values())) == 36
    assert indiapost.state_code("JAMMU AND KASHMIR") == "IN-JK"
    assert indiapost.state_code("Jammu & Kashmir") == "IN-JK"
    assert indiapost.state_code("the dadra and nagar haveli and daman and diu") == "IN-DH"
    assert indiapost.state_code("Atlantis") == ""


def test_branch_offices_are_counted_per_pin_code(tmp_path):
    rows = directory_rows()
    rural = ("Karnataka Circle", "Bengaluru East Region", "Bengaluru East Division")
    district = ("BENGALURU RURAL", "KARNATAKA", "NA", "NA")
    rows += [
        (*rural, "Synthetic Village B.O", "562114", "BO", "Delivery", *district),
        (*rural, "Other Village B.O", "562114", "BO", "Delivery", *district),
    ]
    counts = indiapost.branch_offices(write_directory(tmp_path / "pincode.csv", rows))
    assert counts == {"562114": 2}
