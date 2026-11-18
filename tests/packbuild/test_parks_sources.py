"""The park sources' readers on small synthetic inputs (parks_fixtures): NPS, USFS, PAD-US, CPCAD
and Wikidata, and the tier layers built from them (packbuild.sources.parks)."""

import math

import numpy as np
import parks_fixtures as fx
import pytest

from packbuild.sources.parks import _common, cpcad, nps, padus, usfs, wikidata
from placewise.constants.parks import LOCAL, NATIONAL, POINT_RADIUS_CAP_KM, REGIONAL, STATE
from placewise.model import Outline


def by_park(rows):
    return {r.park: r for r in rows}


def test_nps_units_keep_their_codes_and_tiers(tmp_path):
    rows = by_park(nps.parks(fx.nps_pages(tmp_path / "nps")))
    park = rows["nps:ALPH"]
    assert (park.name, park.tier, park.designation, park.code) == ("Alpha National Park", NATIONAL, "National Park",  # noqa: E501
                                                                   "ALPH")  # fmt: skip
    assert park.aliases == ("Alpha",) and park.source == "nps-boundaries"
    assert park.area_km2 == pytest.approx(0.3 * 0.3 * 111.195**2, rel=0.01)
    # two units under one code: the national park keeps the plain id
    assert rows["nps:ALPH:national-preserve"].name == "Alpha National Preserve"
    # a national monument under 10 km² is a site (tier 3); a big one stays national
    assert rows["nps:TINY"].tier == REGIONAL and rows["nps:BIGM"].tier == NATIONAL
    assert rows["nps:OLDH"].tier == REGIONAL
    assert "nps:XXXX" not in rows  # a unit type without a tier is dropped
    lats = [lat for lat, _ in park.feature.outlines[0].rings[0]]
    assert min(lats) == pytest.approx(0.6) and max(lats) == pytest.approx(0.9)


def test_usfs_forests_and_grasslands(tmp_path):
    rows = by_park(usfs.parks(fx.usfs_shapefile(tmp_path / "usfs")))
    assert rows["usfs:0101"].name == "North National Forest" and rows["usfs:0101"].tier == STATE
    assert rows["usfs:0101"].aliases == ("North",) and rows["usfs:0101"].code == "0101"
    assert rows["usfs:0102"].designation == "National Grassland"
    assert rows["usfs:0103"].aliases == ("Twin Rivers",)  # "National Forests"


def test_padus_parcels_become_parks_by_name_and_place(tmp_path):
    rows = padus.parks(fx.padus_fee_pages(tmp_path / "fee"), fx.padus_refuge_pages(tmp_path / "nwr"))
    parks = {}
    for r in rows:
        parks.setdefault(r.park, []).append(r)
    green = [p for p in parks if ":lp:central-green:" in p]
    assert len(green) == 2  # two clusters: the near parcels are one park, the far one another
    assert sorted(len(parks[p]) for p in green) == [1, 2]
    assert all(p.startswith("pad-us:xx:lp:central-green:") and len(p.rsplit(":", 1)[1]) == 5 for p in green)
    assert {r.tier for p in green for r in parks[p]} == {LOCAL}
    state = next(r for r in rows if r.name == "Gull State Park")
    assert (state.tier, state.designation, state.aliases) == (STATE, "State Park", ("Gull",))
    refuge = next(r for r in rows if r.name == "Heron National Wildlife Refuge")
    assert refuge.tier == STATE and refuge.park.startswith("pad-us:xx:nwr:heron-national-wildlife-refuge:")
    names = {r.name for r in rows}
    # closed to the public, an owner's name, a private designation, an NPS unit (from nps instead)
    assert not names & {"Closed Yard", "City of Nowhere", "Private Woods", "Agency Monument"}
    assert "Mesa Monument" in names  # a BLM national monument
    # generic or placeholder names give way to the parcel's own local name, or the parcel goes
    assert {"Heron Ridge Open Space", "Willow Bend Park"} <= names
    assert not names & {"Open Space", "Open  space", "Unknown Park", "Unknown"}
    assert any(r.park.startswith("pad-us:xx:lp:heron-ridge-open-space:") for r in rows)


def test_padus_ids_are_stable_across_reads(tmp_path):
    first = sorted(r.park for r in padus.parks(fx.padus_fee_pages(tmp_path / "a")))
    assert first == sorted(r.park for r in padus.parks(fx.padus_fee_pages(tmp_path / "b")))


def test_cpcad_keeps_public_protected_areas_grouped_by_parent(tmp_path):
    rows = cpcad.parks(fx.cpcad_pages(tmp_path / "cpcad"))
    parks = {}
    for r in rows:
        parks.setdefault(r.park, []).append(r)
    assert set(parks) == {"cpcad:100", "cpcad:200", "cpcad:400"}  # not 800: "Natural Area" is no name
    pine = parks["cpcad:100"][0]
    assert (pine.name, pine.tier, pine.designation) == ("Pine Lake National Park", NATIONAL, "National Park")
    assert pine.aliases == ("Pine Lake National Park of Canada", "Pine Lake")
    maple = parks["cpcad:200"]  # two zones, one park: the parent's name, the more significant tier
    assert [r.name for r in maple] == ["Maple Provincial Park"] * 2 and {r.tier for r in maple} == {STATE}
    assert parks["cpcad:400"][0].tier == REGIONAL  # NGO-owned, governed by a conservation authority
    lats = [lat for lat, _ in pine.feature.outlines[0].rings[0]]
    assert min(lats) == pytest.approx(45.0, abs=1e-6) and max(lats) == pytest.approx(45.2, abs=1e-6)


def test_wikidata_points_with_radius_and_tier(tmp_path):
    national = fx.wikidata_result(tmp_path / "np.json", [
        ("Q10", "Gamma National Park", -139.6, 2.25, 78.54e6, "XC", 40),
        ("Q10", "Gamma National Park", -139.6, 2.25, 60e6, "XC", 40),
        ("Q11", "Lake National Park", -80.0, 45.0, 1e9, "CA", 50),  # has an outline in can-parks
        ("Q12", "Q12", 10.0, 10.0, None, None, 1),  # no English label
        ("Q13", "Vast National Park", 20.0, 70.0, 972e9, "GL", 30),
    ])  # fmt: skip
    india = fx.wikidata_result(tmp_path / "in.json", [
        ("Q20", "Bhima Wildlife Sanctuary", 74.0, 19.0, None, "IN", 5),
        ("Q21", "Sal Conservation Reserve", 75.0, 20.0, 12e6, "IN", 2),
        ("Q10", "Gamma National Park", -139.6, 2.25, None, "XC", 40),
    ])  # fmt: skip
    layer = wikidata.park_points({"parks_national": national, "parks_india": india})
    cols = layer.columns
    assert cols["id"] == ["wikidata:Q10", "wikidata:Q13", "wikidata:Q20", "wikidata:Q21"]
    assert list(cols["tier"]) == [NATIONAL, NATIONAL, STATE, REGIONAL]
    assert cols["designation"] == ["National Park", "National Park", "Wildlife Sanctuary", "Protected Area"]
    radius = list(cols["radius_km"])
    assert radius[0] == pytest.approx(5.0, rel=1e-3)  # the largest area: 78.54 km²
    assert radius[1] == POINT_RADIUS_CAP_KM and radius[2] == 0.0
    assert math.isnan(cols["area_km2"][2]) and cols["aliases"][0] == "Gamma"
    assert layer.lat[0] == 2.25 and layer.lon[0] == -139.6
    assert "country" not in cols  # parks carry no country: the boundary layers give it


def test_tier_layers_hold_each_park_once_with_its_total_area():
    def row(park, tier, box):
        ring = ((box[0], box[1]), (box[0], box[3]), (box[2], box[3]), (box[2], box[1]))
        return _common.ParkRow(park, park.title(), tier, "Park", _feature(ring), "synthetic")

    rows = [
        row("b", LOCAL, (0, 0, 0.01, 0.01)),
        row("a", NATIONAL, (0, 0, 1, 1)),
        row("b", LOCAL, (1, 1, 1.01, 1.01)),
    ]
    layers = _common.layers(rows)
    assert [layer.name for layer in layers] == ["parks_national", "parks_local"]
    local = layers[1]
    assert local.columns["id"] == ["b", "b#2"] and local.columns["park"] == ["b", "b"]
    assert np.allclose(local.columns["area_km2"], rows[0].area_km2 + rows[2].area_km2, rtol=1e-6)
    assert local.sources == ("synthetic",) and local.cell_deg == _common.CELL_DEG[LOCAL]


def test_outlines_across_the_antimeridian_are_cut_at_180():
    projection = _common.WebMercator
    west = fx.mercator_box(51.0, 179.5, 52.0, 180.5)  # x beyond 180°: the service's continuous coordinates
    feature = _common.feature_of([west], projection, "x")
    lons = sorted({round(lon, 6) for o in feature.outlines for lon in (p[1] for p in o.rings[0])})
    assert len(feature.outlines) == 2 and lons[0] == -180 and lons[-1] == 180
    assert -179.5 in lons and 179.5 in lons


def _feature(ring):
    from placewise.model import Feature

    return Feature((Outline((ring,)),))
