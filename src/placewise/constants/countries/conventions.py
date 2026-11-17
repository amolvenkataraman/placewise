"""How location strings write countries in short, where that differs from plain ISO 3166-1."""

# Alpha-3 codes read in any case as a whole part ("Toronto, Can"), as real-world strings use them; any
# other alpha-3 code must be written in capitals so words like "and" or "per" stay words.
# fmt: off
ALPHA3_ANY_CASE = frozenset({
    "USA", "CAN", "GBR", "IRL", "DEU", "FRA", "NLD", "CHE", "ESP", "ITA", "POL", "ROU", "ISR",
    "IND", "CHN", "HKG", "TWN", "JPN", "KOR", "SGP", "MYS", "PHL", "AUS", "MEX", "BRA", "CRI",
})
# fmt: on

# US state and Canadian province codes also commonly used for a country: "Toronto, CA",
# "Amsterdam, NL", "Pune, IN". Other clashes ("MO" Macao, "PA" Panama, "GA" Gabon) read only as
# the state or province.
STATE_CODES_ALSO_COUNTRIES = frozenset(
    {"CA", "DE", "IN", "IL", "NL", "CO", "AR", "PE", "SK", "PR", "VI", "GU", "AS", "MP"}
)

# Lower-case short forms of a country read without capitals ("remote, uk")
LOWERCASE_SHORT_FORMS = frozenset({"usa", "uk", "uae", "us"})
