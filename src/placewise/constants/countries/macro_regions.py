"""Macro regions that limit remote work ("Remote - EMEA"), as sets of ISO 3166-1 alpha-2 codes.

Europe, Africa, Western Asia (the Middle East), the rest of Asia with Oceania, and Latin America
follow the UN M49 standard country groupings (https://unstats.un.org/unsd/methodology/m49/), with
Taiwan added to Eastern Asia and Kosovo left out (no ISO code). EMEA, APAC and the Americas are
built from them; North America is the US, Canada and Mexico; the EU is its 27 member states.
Worldwide (members None) means no limit.
"""

from ._records import MacroRegion

# fmt: off
_GROUPS = {
    "europe": frozenset({
        "BY", "BG", "CZ", "HU", "PL", "MD", "RO", "RU", "SK", "UA", "AX", "DK", "EE", "FO", "FI", "GG",
        "IS", "IE", "IM", "JE", "LV", "LT", "NO", "SJ", "SE", "GB", "AL", "AD", "BA", "HR", "GI", "GR",
        "VA", "IT", "MT", "ME", "MK", "PT", "SM", "RS", "SI", "ES", "AT", "BE", "FR", "DE", "LI", "LU",
        "MC", "NL", "CH",
    }),
    "africa": frozenset({
        "DZ", "EG", "LY", "MA", "SD", "TN", "EH", "IO", "BI", "KM", "DJ", "ER", "ET", "TF", "KE", "MG",
        "MW", "MU", "YT", "MZ", "RE", "RW", "SC", "SO", "SS", "UG", "TZ", "ZM", "ZW", "AO", "CM", "CF",
        "TD", "CG", "CD", "GQ", "GA", "ST", "BW", "SZ", "LS", "NA", "ZA", "BJ", "BF", "CV", "CI", "GM",
        "GH", "GN", "GW", "LR", "ML", "MR", "NE", "NG", "SH", "SN", "SL", "TG",
    }),
    "western_asia": frozenset({
        "AM", "AZ", "BH", "CY", "GE", "IQ", "IL", "JO", "KW", "LB", "OM", "QA", "SA", "PS", "SY", "TR",
        "AE", "YE",
    }),
    "asia_pacific": frozenset({
        "KZ", "KG", "TJ", "TM", "UZ", "CN", "HK", "MO", "KP", "JP", "MN", "KR", "TW", "BN", "KH", "ID",
        "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN", "AF", "BD", "BT", "IN", "IR", "MV", "NP", "PK",
        "LK", "AU", "NZ", "NF", "CX", "CC", "HM", "FJ", "NC", "PG", "SB", "VU", "GU", "KI", "MH", "FM",
        "NR", "MP", "PW", "UM", "AS", "CK", "PF", "NU", "PN", "WS", "TK", "TO", "TV", "WF",
    }),
    "latin_america": frozenset({
        "AI", "AG", "AW", "BS", "BB", "BQ", "VG", "KY", "CU", "CW", "DM", "DO", "GD", "GP", "HT", "JM",
        "MQ", "MS", "PR", "BL", "KN", "LC", "MF", "VC", "SX", "TT", "TC", "VI", "BZ", "CR", "SV", "GT",
        "HN", "MX", "NI", "PA", "AR", "BO", "BV", "BR", "CL", "CO", "EC", "FK", "GF", "GY", "PY", "PE",
        "GS", "SR", "UY", "VE",
    }),
    "northern_america": frozenset({
        "BM", "CA", "GL", "PM", "US",
    }),
}
# fmt: on

MACRO_REGIONS = (
    MacroRegion(
        "Worldwide",
        (
            "Global",
            "Anywhere",
            "International",
            "Any Location",
            "Everywhere",
            "World",
        ),
        None,
    ),
    MacroRegion(
        "North America",
        (
            "NORAM",
            "US and Canada and Mexico",
        ),
        frozenset({"US", "CA", "MX"}),
    ),
    MacroRegion(
        "Americas",
        (
            "The Americas",
            "AMER",
        ),
        _GROUPS["latin_america"] | _GROUPS["northern_america"],
    ),
    MacroRegion(
        "LATAM",
        (
            "Latin America",
            "Latin America and the Caribbean",
        ),
        _GROUPS["latin_america"],
    ),
    MacroRegion(
        "Europe",
        ("EUR",),
        _GROUPS["europe"],
    ),
    MacroRegion(
        "EU",
        ("European Union",),
        frozenset(
            {
                "AT",
                "BE",
                "BG",
                "HR",
                "CY",
                "CZ",
                "DK",
                "EE",
                "FI",
                "FR",
                "DE",
                "GR",
                "HU",
                "IE",
                "IT",
                "LV",
                "LT",
                "LU",
                "MT",
                "NL",
                "PL",
                "PT",
                "RO",
                "SK",
                "SI",
                "ES",
                "SE",
            }
        ),
    ),
    MacroRegion(
        "EMEA",
        (
            "Europe, Middle East and Africa",
            "Europe Middle East Africa",
        ),
        _GROUPS["europe"] | _GROUPS["africa"] | _GROUPS["western_asia"],
    ),
    MacroRegion(
        "Middle East",
        ("MENA",),
        _GROUPS["western_asia"],
    ),
    MacroRegion(
        "Africa",
        (),
        _GROUPS["africa"],
    ),
    MacroRegion(
        "APAC",
        (
            "Asia Pacific",
            "Asia-Pacific",
            "Asia Pac",
        ),
        _GROUPS["asia_pacific"],
    ),
    MacroRegion(
        "DACH",
        (),
        frozenset({"DE", "AT", "CH"}),
    ),
    MacroRegion(
        "Nordics",
        ("Nordic Countries",),
        frozenset({"DK", "FI", "IS", "NO", "SE"}),
    ),
    MacroRegion(
        "Benelux",
        (),
        frozenset({"BE", "NL", "LU"}),
    ),
    MacroRegion(
        "ANZ",
        (
            "Australia and New Zealand",
            "Australia & New Zealand",
        ),
        frozenset({"AU", "NZ"}),
    ),
)
