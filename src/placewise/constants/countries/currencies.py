"""Currencies (ISO 4217), for inferring from a location which currency amounts are likely in."""

# Main currencies of the countries location search covers most; others are left to a currency table
# (and to the country profile).
# fmt: off
CURRENCIES = {
    "US": "USD", "CA": "CAD", "GB": "GBP", "IE": "EUR", "NL": "EUR", "AU": "AUD", "NZ": "NZD",
    "DE": "EUR", "FR": "EUR", "CH": "CHF", "SE": "SEK", "DK": "DKK", "NO": "NOK", "FI": "EUR",
    "ES": "EUR", "IT": "EUR", "PT": "EUR", "PL": "PLN", "AT": "EUR", "BE": "EUR", "LU": "EUR",
    "SG": "SGD", "HK": "HKD", "JP": "JPY", "KR": "KRW", "IN": "INR", "IL": "ILS",
}
# fmt: on

# Cities taken as a currency hint when no country can be found
CURRENCY_CITY_HINTS = {"Toronto": "CAD", "Vancouver": "CAD", "London": "GBP", "Berlin": "EUR", "Paris": "EUR"}
