"""The names most people need are one import away: placewise.lookup, placewise.Geocoder, placewise.Client."""

import subprocess
import sys

import placewise


def test_headline_names_are_at_the_top_level():
    from placewise.engine import Geocoder, lookup
    from placewise.service import Client

    assert placewise.lookup is lookup and placewise.Geocoder is Geocoder and placewise.Client is Client
    assert {"lookup", "Geocoder", "Client", "load_settings", "load_overrides"} <= set(placewise.__all__)


def test_world_names_are_at_the_top_level():
    from placewise import world

    assert placewise.world is world
    assert placewise.profile is world.profile
    assert placewise.country is world.country and placewise.countries is world.countries
    assert {"world", "profile", "country", "countries"} <= set(placewise.__all__)


def test_importing_placewise_stays_light():
    # the engine (packs, store, config) and the world tables load on first use, not on `import placewise`
    heavy = ("placewise.engine", "placewise.packs", "placewise.world", "placewise.constants.countries")
    code = f"import sys, placewise; print(*[m in sys.modules for m in {heavy!r}])"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.split() == ["False"] * len(heavy)
