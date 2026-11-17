"""Reading the LGD reports (ind_kit writes them in LGD's exact CSV format)."""

import pytest
from ind_kit import write_lgd

from packbuild.ind import lgd


@pytest.fixture
def directory(tmp_path):
    return lgd.read(write_lgd(tmp_path / "lgd"))


def test_states_with_iso_codes(directory):
    assert directory.states["29"].name == "Karnataka" and directory.states["29"].iso == "IN-KA"
    assert directory.states["7"].kind == "union territory" and directory.states["29"].kind == "state"
    assert directory.states["37"].iso == "IN-LA"


def test_districts_and_subdistricts_know_their_state(directory):
    d = directory.districts["572"]
    assert (d.name, d.state, d.iso) == ("Bengaluru Urban", "29", "IN-KA")
    s = directory.subdistricts["4136"]
    assert (s.name, s.parent, s.iso) == ("Mumbai City", "482", "IN-MH")


def test_ulbs_with_type_local_name_and_census_code(directory):
    u = directory.ulbs["251488"]
    assert (u.name, u.local_name, u.kind, u.census2011, u.iso) == (
        "Greater Mumbai", "मोठे मुंबई", "Municipal Corporation", "802794", "IN-MH",
    )  # fmt: skip
    assert directory.ulbs["305851"].census2011 == ""  # LGD writes 0 for none
    assert directory.ulbs["305851"].kind == ""  # no PIN code row names its type


def test_pin_tables(directory):
    assert directory.pin_villages["194101"] == {("39", "6201"): 2}
    assert directory.pin_ulbs["110001"] == {"276447"}
    assert "560001" not in directory.pin_ulbs  # Bengaluru's corporations have no PIN codes in LGD


def test_type_names_are_tidied(tmp_path):
    paths = write_lgd(tmp_path / "lgd", pin_urban=[("251488", "MUNICIPAL CORPORATION", "400001")])
    assert lgd.read(paths).ulbs["251488"].kind == "Municipal Corporation"


def test_refuses_another_report(tmp_path):
    paths = write_lgd(tmp_path / "lgd")
    paths["districts"] = paths["states"]
    with pytest.raises(ValueError, match="District Code"):
        lgd.read(paths)
