from pathlib import Path

import pytest

from packbuild.sources import ourairports

DATA = Path(__file__).parent / "data"


@pytest.fixture
def layer():
    return ourairports.airports(DATA / "airports.csv")


def test_keeps_large_medium_and_scheduled_small_airports(layer):
    assert layer.name == "airports" and layer.kind == "point" and layer.sources == ("ourairports",)
    # dropped: a small airport without scheduled service, a heliport, a seaplane base, a closed one
    assert list(layer.columns["id"]) == [
        "ourairports:CYYZ",
        "ourairports:KRNO",
        "ourairports:VOBL",
        "ourairports:KTVL",  # medium airports stay even without scheduled service
        "ourairports:CJV7",  # small, but scheduled
    ]
    assert list(layer.columns["type"]) == ["large_airport"] * 3 + ["medium_airport", "small_airport"]


def test_columns(layer):
    c = {k: list(v) for k, v in layer.columns.items()}
    assert c["name"][0] == "Toronto Pearson International Airport"
    assert c["iata"] == ["YYZ", "RNO", "BLR", "TVL", "SUR"]
    assert c["municipality"][4] == "Summer Beaver"
    assert c["country"] == ["CA", "US", "IN", "US", "CA"]
    assert c["region"] == ["CA-ON", "US-NV", "IN-KA", "US-CA", "CA-ON"]
    assert c["scheduled"] == [True, True, True, False, True]
    assert c["elevation_ft"] == [569, 4415, 3000, 6264, 832]
    assert (layer.lat[0], layer.lon[0]) == pytest.approx((43.675935, -79.629421))
    assert layer.types["scheduled"] == "bool" and layer.types["elevation_ft"] == "i2"


def test_icao_is_only_ever_a_four_letter_code(layer):
    # Summer Beaver has no ICAO code; its gps_code/ident "CJV7" is a Transport Canada identifier
    assert list(layer.columns["icao"]) == ["CYYZ", "KRNO", "VOBL", "KTVL", ""]


def test_icao_falls_back_to_gps_code_then_ident():
    assert ourairports.icao({"icao_code": "", "gps_code": "EGLL", "ident": "X"}) == "EGLL"
    assert ourairports.icao({"gps_code": "", "ident": "LFPG"}) == "LFPG"  # files without icao_code
    assert ourairports.icao({"icao_code": "", "gps_code": "K00A", "ident": "00A"}) == ""


def test_missing_elevation_is_null(tmp_path):
    src = (DATA / "airports.csv").read_text(encoding="utf-8").splitlines()
    header, pearson = src[0], src[1].replace(",569,", ",,")
    path = tmp_path / "airports.csv"
    path.write_text(header + "\n" + pearson + "\n", encoding="utf-8")
    layer = ourairports.airports(path)
    assert list(layer.columns["elevation_ft"]) == [layer.nulls["elevation_ft"]]


def test_a_changed_header_is_an_error(tmp_path):
    path = tmp_path / "airports.csv"
    path.write_text('"id","ident","name"\n1,"X","Y"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="scheduled_service"):
        ourairports.airports(path)
