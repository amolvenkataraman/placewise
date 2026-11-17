"""Configuration, overrides, attribution, privacy policies and presence counts."""

import datetime as dt

import pytest

from placewise.model import (
    AppPlace,
    AreaSelector,
    BBox,
    DayPresence,
    Layer,
    OverrideSet,
    PackInfo,
    Point,
    PresenceDays,
    PrivacyPolicy,
    PrivacyZone,
    Settings,
    Source,
)


def test_settings_defaults_match_the_documented_defaults():
    s = Settings()
    assert s.worldview.order == ("de_facto",) and not s.worldview.lock
    assert s.names.prefer == "official"
    assert (s.near.park_tier1, s.near.park_tier2, s.near.park_tier3) == (25, 10, 1)
    assert s.near.airport == 10
    assert not s.data.offline and s.data.auto_update == "never"
    assert s.server.host == "127.0.0.1" and not s.server.log_coordinates
    assert s.compliance.clients_block == ()


def test_settings_merge_partial_dicts_and_validate():
    s = Settings.from_dict({"worldview": {"order": ["IN", "de_facto"], "lock": True}, "near": {"airport": 5}})
    assert s.worldview.order == ("IN", "de_facto") and s.worldview.lock
    assert s.near.airport == 5 and s.near.park_tier1 == 25  # untouched defaults survive
    for bad in [
        {"worldview": {"order": ["india"]}},
        {"worldview": {"conflict": "shout"}},
        {"names": {"prefer": "posh"}},
        {"near": {"airport": -1}},
        {"data": {"auto_update": "hourly"}},
        {"mystery": {}},
    ]:
        with pytest.raises(ValueError):
            Settings.from_dict(bad)


def test_area_selector_needs_exactly_one_shape():
    AreaSelector(point=Point(43.46, -80.52), km=1.5)
    AreaSelector(bbox=BBox(43, -81, 44, -80))
    with pytest.raises(ValueError):
        AreaSelector()
    with pytest.raises(ValueError):
        AreaSelector(point=Point(0, 0), km=1, bbox=BBox(0, 0, 1, 1))
    with pytest.raises(ValueError):
        AreaSelector(point=Point(0, 0))  # a point needs a radius


def test_override_set_parses_a_toml_shaped_document():
    doc = {
        "rename": [{"id": "geonames:1277333", "name": "Bangalore"}],
        "label": [
            {
                "within": {"point": {"lat": 43.4643, "lon": -80.5204}, "km": 1.5},
                "fields": {"sublocality": "Uptown Waterloo"},
            }
        ],
        "alias": [{"text": "UW", "means": "wikidata:Q1049470"}],
        "hide": [{"id": "wikidata:Q00000"}],
        "add": [
            {"kind": "landmark", "name": "Lookout", "point": {"lat": 43.7, "lon": -79.2}, "radius_m": 200}
        ],
        "tune": [{"id": "pad-us:1", "tier": 1, "near_km": 30}],
    }
    rules = OverrideSet.from_dict(Layer.LOCAL, doc, origin="mine.toml")
    assert len(rules.rules) == 6
    assert rules.rules[0].origin == "mine.toml#1"
    with pytest.raises(ValueError, match="colour"):
        OverrideSet.from_dict(
            Layer.LOCAL,
            {
                "label": [
                    {
                        "within": {"bbox": {"south": 0, "west": 0, "north": 1, "east": 1}},
                        "fields": {"colour": "red"},
                    }
                ]
            },
        )
    with pytest.raises(ValueError, match="paint"):
        OverrideSet.from_dict(Layer.LOCAL, {"paint": []})


def test_layer_precedence():
    assert Layer.LOCAL.precedence > Layer.APP.precedence > Layer.REPO.precedence > Layer.DATA.precedence


def test_source_licence_gate():
    ok = Source("geonames", "GeoNames", "https://www.geonames.org", "CC-BY-4.0", "GeoNames (CC BY 4.0)")
    assert not ok.share_alike
    osm = Source(
        "openstreetmap",
        "OpenStreetMap",
        "https://www.openstreetmap.org",
        "ODbL-1.0",
        "© OpenStreetMap contributors",
        derived_database="https://example.org/releases/osm",
    )
    assert osm.share_alike
    with pytest.raises(ValueError, match="derived"):
        Source("openstreetmap", "OpenStreetMap", "https://www.openstreetmap.org", "ODbL-1.0", "© OSM")
    with pytest.raises(ValueError, match="deny"):
        Source("wdpa", "WDPA", "https://www.protectedplanet.net", "CC-BY-4.0", "UNEP-WCMC")
    with pytest.raises(ValueError, match="licence"):
        Source("x", "X", "https://x.org", "CC-BY-NC-4.0", "X")
    pack = PackInfo("world", "2026.11", 1, "ab" * 32, 30_000_000, ("geonames",))
    assert PackInfo.from_dict(pack.to_dict()) == pack


def test_privacy_policy_validation():
    zone = PrivacyZone("home", Point(43.6532, -79.3832), radius_m=300)
    policy = PrivacyPolicy(zones=(zone,), trim_m=200, trim_jitter_m=100, cloak_min_population=50_000)
    assert PrivacyPolicy.from_dict(policy.to_dict()) == policy
    for bad in [{"trim_m": -1}, {"time_resolution": "fortnight"}, {"snap_m": 0}]:
        with pytest.raises(ValueError):
            PrivacyPolicy(**bad)


def test_app_place_and_presence_days():
    home = AppPlace("home", 43.6532, -79.3832, radius_m=150)  # Toronto City Hall as a stand-in
    assert home.point == Point(43.6532, -79.3832)
    t = dt.datetime(2026, 6, 14, 12, tzinfo=dt.timezone.utc)
    days = PresenceDays(
        by="country",
        rule="any_part",
        days=(
            DayPresence(dt.date(2026, 6, 14), ("CA", "US"), t, t + dt.timedelta(hours=9)),
            DayPresence(dt.date(2026, 6, 15), ("US",), t, t),
            DayPresence(dt.date(2025, 6, 15), ("US",), t, t),
        ),
    )
    assert days.totals() == {"CA": 1, "US": 3}
    assert days.totals(year=2026) == {"CA": 1, "US": 2}
    assert days.evidence("CA", dt.date(2026, 6, 14)).last_fix == t + dt.timedelta(hours=9)
    assert days.evidence("CA", dt.date(2026, 6, 15)) is None
    assert PresenceDays.from_dict(days.to_dict()) == days


def test_data_settings_index_url():
    assert Settings().data.index_url is None
    s = Settings.from_dict({"data": {"index_url": "https://mirror.example/placewise/index.json"}})
    assert s.data.index_url == "https://mirror.example/placewise/index.json"
