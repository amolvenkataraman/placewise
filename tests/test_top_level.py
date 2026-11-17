"""The names most people need are one import away: placewise.lookup, placewise.Geocoder, placewise.Client."""

import subprocess
import sys

import placewise


def test_headline_names_are_at_the_top_level():
    from placewise.client import Client
    from placewise.engine import Geocoder, lookup

    assert placewise.lookup is lookup and placewise.Geocoder is Geocoder and placewise.Client is Client
    assert {"lookup", "Geocoder", "Client", "load_settings", "load_overrides"} <= set(placewise.__all__)


def test_importing_placewise_stays_light():
    # the engine (packs, store, config) loads on first use, not on `import placewise`
    code = "import sys, placewise; print('placewise.engine' in sys.modules, 'placewise.packs' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.split() == ["False", "False"]
