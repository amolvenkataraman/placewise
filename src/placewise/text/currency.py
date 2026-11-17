"""Which currency amounts for a location are likely in (data: constants.countries.currencies)."""

from placewise.constants._keys import key
from placewise.constants.countries.currencies import CURRENCIES, CURRENCY_CITY_HINTS


def currency_for(parsed, default="USD"):
    """The ISO 4217 currency pay for this location is likely in: USD
    when the US is among the places, else the first place's country's currency, else a city hint
    ("Toronto" -> CAD), else `default`."""
    found = list(parsed.countries)
    found += [entry.split("-", 1)[0] for entry in parsed.remote_scope if len(entry.split("-", 1)[0]) == 2]
    if "US" in found:
        return "USD"
    for code in found:
        if code in CURRENCIES:
            return CURRENCIES[code]
    hints = {key(city): currency for city, currency in CURRENCY_CITY_HINTS.items()}
    for part in parsed.parts:
        if part.city and key(part.city) in hints:
            return hints[key(part.city)]
    return default
