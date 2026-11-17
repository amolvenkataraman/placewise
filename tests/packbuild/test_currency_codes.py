"""packbuild.currency_codes: CLDR currencyData -> constants/countries/currency_codes.py."""

import pytest
from facts_kit import DATA

from packbuild import currency_codes as cc


def test_codes_take_the_first_current_tender():
    table = cc.codes(DATA / "cldr" / "currencyData.json", countries=("AQ", "CA", "IN", "SV", "US"))
    assert table == {"CA": "CAD", "IN": "INR", "SV": "USD", "US": "USD"}  # AQ has none


def test_render_round_trips():
    text = cc.render({"CA": "CAD", "US": "USD"}, "49.0.0")
    assert text.startswith('"""GENERATED from Unicode CLDR 49.0.0 currencyData')
    namespace = {}
    exec(compile(text, "currency_codes.py", "exec"), namespace)
    assert namespace["CURRENCY_CODES"] == {"CA": "CAD", "US": "USD"}


@pytest.mark.skipif(not cc.cached_path().exists(), reason="CLDR currencyData not downloaded")
def test_the_module_matches_the_cached_source():
    release = cc.url("cldr", "currency_data").split("/cldr-json/")[1].split("/")[0]
    assert cc.MODULE.read_text(encoding="utf-8") == cc.render(cc.codes(cc.cached_path()), release), (
        "constants/countries/currency_codes.py is out of date: run python -m packbuild.currency_codes"
    )
    assert cc.main(["--check"]) == 0
