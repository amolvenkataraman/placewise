"""How the Geocoder uses country packs: only inside their country, world-only answers unchanged,
curated regions preferred, packs from the store, batch == single."""

import numpy as np
import pytest
from naming_kit import regions_layer, write_ca, write_us

from placewise.engine import Geocoder
from placewise.model import PlaceKind

POINTS = [
    (10.52, -149.28), (10.2, -149.85), (10.05, -149.43), (10.45, -149.2), (10.15, -149.05), (10.705, -149.8),
    (10.75, -149.495), (10.75, -149.45), (10.48, -148.8), (10.25, -148.6), (10.1, -148.2), (10.89, -148.6),
    (10.62, -148.3), (10.72, -148.05), (10.86, -148.3), (10.4, -148.015), (10.45, -147.8), (10.8, -147.1),
    (10.6, -149.88), (9.9, -149.5), (12.0, -148.0),
]  # fmt: skip


def test_country_names_are_the_iso_short_names(geo, world_only):
    for g in (geo, world_only):
        r = g.lookup(10.52, -149.28)
        assert r.country.name == "United States" and r.cc == "US"
        assert r.country.aliases == ("United States of America",)


def test_world_only_keeps_locality_and_city_from_geonames(world_only):
    r = world_only.lookup(10.52, -149.28)
    assert r.locality is r.city and r.city.id.startswith("geonames:")
    assert r.admin2 is None and r.postal is None and r.sublocality is None and r.regions == ()
    assert r.sources["city"] == r.sources["locality"] == "world/cities:score"


def test_country_packs_apply_only_inside_their_country(packs):
    """A US pack whose counties spill over the border never names a Canadian point."""
    geo = Geocoder(packs=list(packs))
    r = geo.lookup(10.48, -148.8)
    assert r.cc == "CA" and r.admin2.name == "Peel"
    assert not any(v.startswith("us/") for v in r.sources.values())


def test_data_version_lists_every_pack(geo):
    assert geo.data_version == "world-2026.11+us-2026.11+ca-2026.11+in-2026.11"


def test_curated_regions_join_metro_areas_smallest_first(tmp_path, packs):
    gta = ((10, -149, 10.9, -148.5), "region:gta", "GTA", "vernacular", "CA")
    golden = ((10, -149, 11, -148), "region:golden-horseshoe", "Golden Horseshoe", "vernacular", "CA")
    ca = write_ca(tmp_path, regions=regions_layer([golden, gta]))
    geo = Geocoder(packs=[packs[0], ca])
    r = geo.lookup(10.25, -148.6)
    assert [p.id for p in r.regions] == ["region:gta", "statcan:35535", "region:golden-horseshoe"]
    assert r.regions[0].kind == PlaceKind.REGION and r.regions[0].codes["kind"] == "vernacular"
    assert r.sources["regions"] == "ca/regions:polygon"  # the smallest one's layer
    fort_erie = geo.lookup(10.1, -148.2)
    assert [p.id for p in fort_erie.regions] == ["statcan:35539", "region:golden-horseshoe"]
    assert fort_erie.sources["regions"] == "ca/cma:polygon"
    # the CMA still names the city it rolls up to, whatever regions the Result lists
    assert r.city.name == "Toronto"


def test_curated_regions_leave_the_metro_city_rule_alone(tmp_path, packs):
    vegas = ((10, -150, 10.5, -149.4), "region:las-vegas", "Las Vegas Valley", "metro", "US")
    us = write_us(tmp_path, regions=regions_layer([vegas]))
    r = Geocoder(packs=[packs[0], us]).lookup(10.27, -149.85)
    assert r.locality.name == "Las Vegas" and r.sources["locality"] == "us/places:metro"
    assert {p.id for p in r.regions} == {"region:las-vegas", "census:cbsa:29820", "census:csa:332"}


def test_label_template_reaches_the_new_fields(packs):
    from placewise.model import LabelSettings, Settings

    settings = Settings(
        label=LabelSettings(template="{sublocality}, {borough}, {locality}, {postal}, {region}")
    )
    r = Geocoder(packs=list(packs), settings=settings).lookup(10.705, -149.8)
    assert r.label == "Williamsfield, Brooklyn, New York, New York-Newark-Jersey City, NY-NJ Metro Area"
    city_style = Settings(label=LabelSettings(style="city"))
    assert (
        Geocoder(packs=list(packs), settings=city_style).lookup(10.25, -148.6).label
        == "Toronto, Ontario, Canada"
    )


def test_default_geocoder_opens_installed_country_packs(packs):
    world, ca = packs[0], packs[2]

    class FakeStore:
        def ensure(self, name):
            assert name == "world"
            return world

        def installed(self):
            return {"world": ["2026.11"], "ca": ["2026.11"], "other": ["1"]}

        def current(self, name):
            return {"ca": ca}[name]

    geo = Geocoder(store=FakeStore())
    assert geo.data_version == "world-2026.11+ca-2026.11"
    assert geo.lookup(10.48, -148.8).locality.name == "Mississauga"


def test_default_geocoder_skips_country_packs_it_cannot_open(packs):
    class PinnedStore:
        def ensure(self, name):
            return packs[0]

        def installed(self):
            return {"world": ["2026.11"], "ca": ["2025.01"]}

        def current(self, name):
            raise LookupError(f"{name} is not installed at the pinned version")

    assert Geocoder(store=PinnedStore()).data_version == "world-2026.11"


@pytest.mark.parametrize("subset", ["all", "us"])
def test_lookup_many_equals_lookup(packs, subset):
    geo = Geocoder(packs=list(packs) if subset == "all" else [packs[0], packs[1]])
    lats, lons = np.array([p[0] for p in POINTS]), np.array([p[1] for p in POINTS])
    many = geo.lookup_many(lats, lons)
    for r, a, b in zip(many, lats, lons, strict=True):
        assert r.to_dict() == geo.lookup(float(a), float(b)).to_dict()


def test_a_country_without_its_pack_keeps_the_world_answer(packs, world_only):
    geo = Geocoder(packs=[packs[0], packs[1]])  # world and us only
    with_us, alone = geo.lookup(10.25, -148.6).to_dict(), world_only.lookup(10.25, -148.6).to_dict()
    assert with_us.pop("data_version") == "world-2026.11+us-2026.11"
    alone.pop("data_version")
    assert with_us == alone
