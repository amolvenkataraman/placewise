"""currency_for: the currency amounts for a location are likely in."""

import pytest

from placewise.text import currency_for, parse_location


@pytest.mark.parametrize(
    ("text", "currency"),
    [
        ("Toronto, ON", "CAD"),
        ("San Francisco, CA; Toronto, ON", "USD"),  # the US among the countries: USD
        ("Toronto, ON; Austin, TX", "USD"),
        ("London, UK", "GBP"),
        ("Berlin, Germany", "EUR"),
        ("Bengaluru, Karnataka", "INR"),
        ("Toronto, CA", "CAD"),  # a known city settles the code
        ("Toronto", "CAD"),  # city hints
        ("Vancouver", "CAD"),
        ("Somewhere", "USD"),  # the default
        ("Remote - Canada", "CAD"),
    ],
)
def test_currency_for(text, currency):
    assert currency_for(parse_location(text)) == currency


def test_currency_for_default():
    assert currency_for(parse_location("Somewhere"), default=None) is None
