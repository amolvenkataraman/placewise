"""packbuild.ind.names (the curated names of Indian units) and packbuild.ind.places (neighbourhoods
from post-office names). Public post offices; coordinates approximate."""

import json

import numpy as np
import pytest

from packbuild.ind import names, places
from packbuild.ind.lgd import Directory, Unit
from packbuild.layer import LayerData

SOURCE = {"title": "A notification", "url": "https://example.org/n"}


def write(tmp_path, units=(), cities=(), words=()):
    doc = {
        "_comment": "test",
        "units": list(units),
        "cities": list(cities),
        "not_neighbourhoods": list(words),
    }
    path = tmp_path / "ind.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def directory():
    d = Directory()
    d.states = {"6": Unit("6", "Haryana", "", "IN-HR")}
    d.districts = {"62": Unit("62", "Gurugram", "6", "IN-HR")}
    d.ulbs = {"248576": Unit("248576", "Gurugram", "6", "IN-HR")}
    return d


GURUGRAM = {
    "lgd": "district:62",
    "name": "Gurugram",
    "former": [{"name": "Gurgaon", "until": "2016"}],
    "aliases": ["Gurgaon District"],
    "source": SOURCE,
}


def test_names_by_lgd_code(tmp_path):
    n = names.load(write(tmp_path, [GURUGRAM], words=["College"]))
    assert n.name("district", "62") == "Gurugram" and n.name("district", "63", "x") == "x"
    assert n.other_names("district", "62") == ("Gurgaon", "Gurgaon District")
    assert n.district_aliases(directory()) == {("IN-HR", "GURGAON"): "62", ("IN-HR", "GURGAONDISTRICT"): "62"}
    assert n.not_neighbourhoods == ("College",)
    n.check(directory())


def test_check_names_codes_lgd_lacks_and_stale_lgd_names(tmp_path):
    stale = {**GURUGRAM, "lgd_name": "Gurgaon"}
    missing = {"lgd": "ulb:1", "name": "Nowhere", "source": SOURCE}
    with pytest.raises(ValueError, match=r"(?s)district:62: LGD now says 'Gurugram'.*ulb:1 \(Nowhere\)"):
        names.load(write(tmp_path, [stale, missing])).check(directory())


@pytest.mark.parametrize(
    "entry",
    [
        {"lgd": "district:x", "name": "A", "source": SOURCE},
        {"lgd": "district:1", "name": "", "source": SOURCE},
        {"lgd": "district:1", "name": "A", "source": {"title": "t", "url": "http://insecure"}},
    ],
)
def test_units_need_a_code_a_name_and_a_source(tmp_path, entry):
    with pytest.raises(ValueError, match="needs lgd kind:code"):
        names.load(write(tmp_path, [entry]))


def test_cities_need_an_lgd_id(tmp_path):
    with pytest.raises(ValueError, match="needs an lgd:ulb id"):
        names.load(write(tmp_path, cities=[{"id": "x", "name": "B", "lgd": ["1"], "source": SOURCE}]))


@pytest.mark.parametrize(
    ("office", "name"),
    [
        ("Koramangala S.O", "Koramangala"),
        ("Indiranagar S.O (Bengaluru)", "Indiranagar"),
        ("Whitefield S.O", "Whitefield"),
        ("St. Johns Medical College S.O", ""),  # an institution
        ("Gandhi Bazar SO Amritsar", "Gandhi Bazar"),
        ("110001 S.O", ""),
    ],
)
def test_neighbourhood_names(office, name):
    assert places.neighbourhood_name(office, ("Medical College", "High Court")) == name


def test_one_neighbourhood_per_city_and_name_preferring_bigger_offices():
    rows = [  # (name, pincode, type, delivery, lat, lon)
        ("Koramangala VI Bk S.O", "560095", "PO", True, 12.934, 77.623),
        ("Koramangala S.O", "560034", "PO", True, 12.935, 77.624),
        ("Koramangala B.O", "560034", "BO", True, 12.936, 77.625),
        ("Bangalore S.O", "560001", "PO", True, 12.98, 77.60),  # the city's former name
        ("Vidhana Soudha S.O", "560001", "PO", False, 12.979, 77.591),
        ("Hoskote S.O", "562114", "PO", True, 13.07, 77.80),  # no city
    ]
    offices = LayerData(
        "post_offices",
        "point",
        {
            "id": [f"indiapost:{r[1]}:{r[0]}" for r in rows],
            "name": [r[0] for r in rows],
            "pincode": [r[1] for r in rows],
            "office_type": [r[2] for r in rows],
            "delivery": [r[3] for r in rows],
        },
        ("indiapost-pincode-directory",),
        lat=np.array([r[4] for r in rows]),
        lon=np.array([r[5] for r in rows]),
    )
    city = {p: "lgd:ulb:276600" for p in ("560095", "560034", "560001")}
    layer = places.neighbourhoods(offices, city, {"lgd:ulb:276600": ("Bengaluru", "Bangalore")})
    assert layer.columns["name"] == ["Koramangala VI Bk", "Koramangala", "Vidhana Soudha"]
    assert layer.columns["office"][1] == "Koramangala S.O" and layer.columns["city"] == ["lgd:ulb:276600"] * 3
    assert layer.sources == ("indiapost-pincode-directory", "lgd-directory")
