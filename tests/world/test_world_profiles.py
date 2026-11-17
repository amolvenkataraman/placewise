"""world.profile: a country's (or subregion's) facts and conventions, read from the world pack's
country_facts layer (built from GeoNames, Unicode CLDR and Wikidata)."""

from pathlib import Path

import pytest
from world_kit import write_world

from placewise import world
from placewise.model import Profile
from placewise.packs import LayerData, open_pack
from placewise.store import Store

REAL = Path(__file__).resolve().parents[2] / ".cache" / "packbuild" / "out" / "world-2026.11"


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    return write_world(tmp_path_factory.mktemp("packs"))


def test_canada(pack):
    ca = world.profile("CA", pack=pack)
    assert isinstance(ca, Profile)
    assert (ca.code, ca.alpha2, ca.alpha3, ca.name, ca.kind) == ("CA", "CA", "CAN", "Canada", "country")
    assert ca.currency.code == "CAD" and ca.currency.name == "Canadian Dollar"
    assert ca.currency.symbol == "CA$" and ca.currency.narrow_symbol == "$"
    assert ca.calling_code == "+1" and ca.measurement_system == "metric"
    assert ca.capital == "Ottawa" and ca.continent == "North America" and ca.tld == ".ca"
    assert ca.languages == ("en-CA", "fr-CA", "iu") and ca.neighbours == ("US",)
    assert "America/Toronto" in ca.time_zones
    assert (ca.population.value, ca.population.source, ca.population.year) == (41651653, "geonames", None)
    assert ca.area_km2.value == 9984670
    assert (ca.driving_side, ca.first_day_of_week) == ("right", "sunday")
    assert (ca.date_format, ca.locale) == ("y-MM-dd", "en-CA")


def test_us_uk_india(pack):
    assert world.profile("US", pack=pack).measurement_system == "US"
    gb = world.profile("United Kingdom", pack=pack)
    assert gb.driving_side == "left" and gb.measurement_system == "imperial-mixed"
    india = world.profile("IND", pack=open_pack(pack))  # an opened Pack works too
    assert india.currency.code == "INR" and india.calling_code == "+91"


def test_missing_values_are_none_not_invented(pack):
    aq = world.profile("AQ", pack=pack)
    assert aq.currency is None and aq.calling_code is None and aq.capital is None
    assert aq.population.value == 0 and aq.time_zones == ()
    fr = world.profile("France", pack=pack)  # no row in this pack: only the code table's fields
    assert (fr.alpha3, fr.name, fr.currency, fr.capital) == ("FRA", "France", None, None)


def test_subregion_profile_carries_only_country_wide_facts(pack):
    on = world.profile("CA-ON", pack=pack)
    assert (on.code, on.name, on.kind, on.alpha2) == ("CA-ON", "Ontario", "province", "CA")
    assert on.currency.code == "CAD" and on.calling_code == "+1" and on.driving_side == "right"
    assert on.capital is None and on.population is None and on.time_zones == () and on.languages == ()
    assert world.profile("Karnataka", pack=pack).currency.code == "INR"


def test_unknown_place(pack):
    with pytest.raises(KeyError, match="Narnia"):
        world.profile("Narnia", pack=pack)


def test_no_pack_offline_names_the_install_command(tmp_path):
    from placewise.model import DataSettings

    store = Store(data_dir=tmp_path / "data", settings=DataSettings(offline=True))
    with pytest.raises(LookupError, match="placewise data install world"):
        world.profile("CA", store=store)


def test_a_pack_without_the_layer_says_so(tmp_path):
    other = LayerData("things", "point", {"id": ["x:1"], "name": ["X"]}, ("geonames",), lat=[0.0], lon=[0.0])
    with pytest.raises(LookupError, match="country_facts"):
        world.profile("CA", pack=write_world(tmp_path, [other]))


@pytest.mark.skipif(not (REAL / "country_facts").exists(), reason="world pack not built")
def test_the_built_world_pack():
    ca = world.profile("CA", pack=REAL)
    assert ca.currency.code == "CAD" and ca.calling_code == "+1" and ca.measurement_system == "metric"
    assert world.profile("US", pack=REAL).measurement_system == "US"
    assert world.profile("GB", pack=REAL).driving_side == "left"
    assert world.profile("IN", pack=REAL).currency.code == "INR"
    for c in world.countries():
        assert world.profile(c.alpha2, pack=REAL).name == c.name


def test_lazy_top_level_profile():
    import placewise

    assert placewise.profile is world.profile


def test_profile_uses_the_configured_store(monkeypatch, tmp_path):
    # placewise.toml / env decide where the world pack comes from, as they do for lookup
    import placewise.config
    import placewise.store
    from placewise.model import DataSettings, Settings

    seen = {}

    class FakeStore:
        def __init__(self, data_dir=None, settings=None, index_url=None):
            seen["settings"] = settings

        def ensure(self, name):
            raise placewise.store.StoreError("no pack in this test")

    settings = Settings(data=DataSettings(data_dir=str(tmp_path / "configured")))
    monkeypatch.setattr(placewise.config, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(placewise.store, "Store", FakeStore)
    with pytest.raises(LookupError):
        world.profile("CA")
    assert seen["settings"] == settings.data
