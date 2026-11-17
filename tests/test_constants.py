import pytest

from placewise.constants import distance, earth, geohash, licences, speed, web_mercator, wgs84


def test_wgs84_defining_and_derived_values():
    assert wgs84.A_M == 6378137.0
    assert wgs84.F == 1 / 298.257223563
    assert wgs84.B_M == pytest.approx(6356752.314245, abs=1e-6)
    assert wgs84.E2 == pytest.approx(0.00669437999014, abs=1e-14)


def test_earth_mean_radius_is_the_iugg_value():
    assert earth.MEAN_RADIUS_KM == 6371.0088


def test_unit_tables_use_exact_definitions():
    assert distance.METRES_PER["mi"] == 1609.344  # international mile
    assert distance.METRES_PER["nmi"] == 1852
    assert speed.METRES_PER_SECOND["kn"] == pytest.approx(1852 / 3600)


def test_web_mercator_limit_makes_the_world_square():
    assert web_mercator.MAX_LAT == pytest.approx(85.0511287798066)


def test_geohash_alphabet_skips_ambiguous_letters():
    assert len(geohash.ALPHABET) == 32
    assert not set("ailo") & set(geohash.ALPHABET)


def test_crs_registry_codes_and_names():
    from placewise.constants import crs

    assert crs.WGS84_2D.epsg == 4326 and crs.WGS84_2D.name == "WGS 84"
    assert crs.WGS84_3D.epsg == 4979
    assert crs.ECEF.epsg == 4978
    assert crs.WEB_MERCATOR.epsg == 3857 and "Web Mercator" in crs.WEB_MERCATOR.common_names
    # the easting-first axis order placewise returns, not the northing-first 32661 / 32761
    assert crs.UPS_NORTH.epsg == 5041 and crs.UPS_SOUTH.epsg == 5042
    assert crs.MGRS.epsg is None  # a grid reference, not a CRS


def test_utm_epsg_codes():
    from placewise.constants import crs

    assert crs.utm_epsg(17, "N") == 32617  # Toronto
    assert crs.utm_epsg(43, "N") == 32643  # Bengaluru
    assert crs.utm_epsg(56, "S") == 32756  # Sydney
    for bad in [(0, "N"), (61, "N"), (17, "X")]:
        with pytest.raises(ValueError):
            crs.utm_epsg(*bad)


def test_unicode_licence_v3_is_accepted_and_permissive():
    # CLDR's licence (SPDX Unicode-3.0): attribution only, so not share-alike
    assert "Unicode-3.0" in licences.KNOWN
    assert "Unicode-3.0" not in licences.SHARE_ALIKE | licences.NEEDS_DERIVED_DATABASE


def test_rejected_water_sources_can_never_be_registered():
    from placewise.constants import water

    # IHO Sea Areas are CC BY-NC-SA (non-commercial); HydroRIVERS forbids stand-alone redistribution
    assert set(water.REJECTED) == {"marineregions-iho", "hydrorivers"}
    assert set(water.REJECTED) <= licences.DENIED_SOURCES
