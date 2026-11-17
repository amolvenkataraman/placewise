"""Small additions to the override rule types: place / country areas, area matching over arrays,
CityRule and Add with an area, and loader errors that name the file and rule number."""

import numpy as np
import pytest

from placewise.model import Add, AreaSelector, BBox, CityRule, Layer, OverrideSet, Point

TORONTO = (43.6532, -79.3832)
MISSISSAUGA = (43.5890, -79.6441)
SAN_FRANCISCO = (37.7793, -122.4193)


def test_area_selector_place_and_country():
    AreaSelector(place="wikidata:Q172")
    AreaSelector(country="ca")
    assert AreaSelector(country="ca").country == "CA"
    with pytest.raises(ValueError):
        AreaSelector(place="wikidata:Q172", country="CA")
    with pytest.raises(ValueError):
        AreaSelector(country="Canada")


def test_area_selector_matches_scalars_and_arrays():
    near_toronto = AreaSelector(point=Point(*TORONTO), km=5)
    assert near_toronto.matches(*TORONTO) is True
    assert near_toronto.matches(*MISSISSAUGA) is False
    lats = np.array([TORONTO[0], MISSISSAUGA[0], SAN_FRANCISCO[0]])
    lons = np.array([TORONTO[1], MISSISSAUGA[1], SAN_FRANCISCO[1]])
    assert near_toronto.matches(lats, lons).tolist() == [True, False, False]

    gta_box = AreaSelector(bbox=BBox(43.4, -80.0, 44.0, -79.0))
    assert gta_box.matches(lats, lons).tolist() == [True, True, False]

    canada = AreaSelector(country="CA")
    assert canada.matches(*TORONTO, cc="CA") is True
    assert canada.matches(*TORONTO, cc=None) is False
    assert canada.matches(lats, lons, cc=np.array(["CA", "CA", "US"])).tolist() == [True, True, False]

    toronto_id = AreaSelector(place="wikidata:Q172")
    assert toronto_id.matches(*TORONTO, place_ids={"wikidata:Q172", "wikidata:Q1904"}) is True
    assert toronto_id.matches(*MISSISSAUGA, place_ids={"wikidata:Q50816"}) is False
    per_point = [{"wikidata:Q172"}, {"wikidata:Q50816"}, set()]
    assert toronto_id.matches(lats, lons, place_ids=per_point).tolist() == [True, False, False]


def test_area_selector_geojson_resolves_relative_to_base_dir(tmp_path):
    (tmp_path / "box.geojson").write_text(
        '{"type": "Polygon", "coordinates": [[[-80, 43.4], [-79, 43.4], [-79, 44], [-80, 44], [-80, 43.4]]]}'
    )
    area = AreaSelector(geojson="box.geojson")
    assert area.matches(*TORONTO, base_dir=tmp_path) is True
    assert area.matches(*SAN_FRANCISCO, base_dir=tmp_path) is False


def test_city_rule_by_locality_or_area():
    CityRule("wikidata:Q17042", "Bay Area")  # positional order unchanged: locality, city
    CityRule(within=AreaSelector(bbox=BBox(37.2, -122.6, 38.3, -121.6)), city="Bay Area")
    with pytest.raises(ValueError):
        CityRule(city="Bay Area")  # neither
    with pytest.raises(ValueError):
        CityRule("wikidata:Q17042", "Bay Area", within=AreaSelector(country="US"))  # both
    with pytest.raises(ValueError):
        CityRule("wikidata:Q17042")  # no city


def test_add_may_match_an_area_instead_of_its_radius():
    rule = Add(
        kind="park",
        name="Toronto Islands",
        point=Point(43.6205, -79.3780),
        within=AreaSelector(bbox=BBox(43.60, -79.40, 43.635, -79.34)),
    )
    assert rule.within is not None
    doc = Add.from_dict(rule.to_dict())
    assert doc == rule


def test_loader_errors_name_the_file_and_rule_number():
    doc = {
        "alias": [{"text": "GTA", "means": "region:gta"}],
        "rename": [{"id": "x", "name": "Y"}, {"id": "y", "nmae": "Z"}],
    }
    with pytest.raises(ValueError, match=r"local:mine\.toml.*#3.*nmae"):
        OverrideSet.from_dict(Layer.LOCAL, doc, origin="local:mine.toml")
    with pytest.raises(ValueError, match=r"local:mine\.toml.*#2.*\[\[paint\]\]"):
        OverrideSet.from_dict(Layer.LOCAL, {"hide": [{"id": "a"}], "paint": [{}]}, origin="local:mine.toml")
    with pytest.raises(ValueError, match=r"#1.*name"):  # missing required field
        OverrideSet.from_dict(Layer.LOCAL, {"rename": [{"id": "x"}]}, origin="f.toml")
    with pytest.raises(ValueError, match=r"\[\[rename\]\]"):  # [rename] instead of [[rename]]
        OverrideSet.from_dict(Layer.LOCAL, {"rename": {"id": "x", "name": "y"}}, origin="f.toml")
