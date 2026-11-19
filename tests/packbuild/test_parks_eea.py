"""EEA Nationally designated areas (packbuild.sources.parks.eea) on natda_kit's small GeoPackage."""

import pytest
from natda_kit import write_natda

from packbuild.sources.parks import eea
from placewise.constants.parks import NATIONAL, REGIONAL, STATE
from placewise.geo.shapes import contains


@pytest.fixture
def rows(tmp_path):
    return eea.parks(write_natda(tmp_path / "natda"))


def _parks(rows):
    out = {}
    for r in rows:
        out.setdefault(r.park, []).append(r)
    return out


def test_tiers_names_and_what_is_left_out(rows):
    parks = _parks(rows)
    assert sorted(parks) == ["eea:101", "eea:103", "eea:104", "eea:105", "eea:109"]
    # left out: a reserve under 1 km² (106), a Natura 2000 site (107), a site with only a point (108)
    alpha = parks["eea:101"]
    assert [r.tier for r in alpha] == [NATIONAL, NATIONAL]  # its zone (102) is part of it
    assert {r.name for r in alpha} == {"Alpha National Park"}  # Wikidata's English label, oldest item
    assert alpha[0].aliases == ("Alpha", "Nationalpark Alpha Kernzone")
    assert alpha[0].designation == "National Park" and alpha[0].source == "eea-natda"
    beta = parks["eea:103"][0]  # touches Alpha's zone, but another name: another park
    assert (beta.name, beta.aliases) == ("Beta", ())
    delta = parks["eea:104"][0]
    assert (delta.tier, delta.designation) == (STATE, "Nature Park")
    epsilon = parks["eea:105"][0]
    assert (epsilon.name, epsilon.tier, epsilon.designation) == ("Epsilon", REGIONAL, "Nature Reserve")


def test_countries_use_iso_codes(rows):
    assert eea.countries(rows) == ["GR", "XX"]  # the EEA's EL is Greece


def test_outlines_are_unprojected_with_holes_kept(rows):
    alpha = next(r for r in rows if r.park == "eea:101" and r.feature.id == "eea:101")
    (outline,) = alpha.feature.outlines
    assert len(outline.rings) == 2  # shell and hole, whichever way the file winds them
    lats = [p[0] for p in outline.rings[0]]
    lons = [p[1] for p in outline.rings[0]]
    assert min(lats) == pytest.approx(45.0, abs=1e-6) and max(lons) == pytest.approx(-9.8, abs=1e-6)
    assert contains(outline.rings, 45.15, -9.85)
    assert not contains(outline.rings, 45.075, -9.925)  # in the hole
    assert alpha.area_km2 == pytest.approx(22.24 * 15.71 - 5.56 * 3.93, rel=0.01)  # less the hole


def test_wdpa_names_take_the_oldest_item(tmp_path):
    _, labels = write_natda(tmp_path / "natda")
    assert eea.wdpa_names(labels) == {
        101: ("Q900", "Alpha National Park"),
        999999: ("Q901", "Somewhere Else"),
    }


def test_a_cut_off_wikidata_answer_says_so(tmp_path):
    path = tmp_path / "wikidata"
    path.write_text('?wdpa\t?item\t?name\n"915"\t<http://www.wikidata.org/entity/Q83397>\n')
    with pytest.raises(ValueError, match="a row has 2 cells"):
        eea.wdpa_names(path)
