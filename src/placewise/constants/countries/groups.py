"""GENERATED from datasets/country_groups by packbuild.country_groups; do not edit.

Regenerate with `uv run python -m packbuild.country_groups`. Each group carries its source and
notes; the reasoning behind single memberships (member notes, other sources) stays in the datasets.
"""

# fmt: off

# date the memberships were checked against their sources
AS_OF = "2026-11-17"

# id -> {name, aliases, kind, members, source, notes}; members are ISO 3166-1 alpha-2 codes
GEOGRAPHIC = {
    "geo:africa": {
        "name": "Africa",
        "aliases": ("African continent",),
        "kind": "continent",
        "members": (
            "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV", "DJ", "DZ", "EG", "EH", "ER",
            "ET", "GA", "GH", "GM", "GN", "GQ", "GW", "IO", "KE", "KM", "LR", "LS", "LY", "MA", "MG", "ML",
            "MR", "MU", "MW", "MZ", "NA", "NE", "NG", "RE", "RW", "SC", "SD", "SH", "SL", "SN", "SO", "SS",
            "ST", "SZ", "TD", "TF", "TG", "TN", "TZ", "UG", "YT", "ZA", "ZM", "ZW",
        ),
        "source": "convention",
        "notes": (
            "Seven-continent convention (Africa, Antarctica, Asia, Europe, North America, Oceania, South "
            "America), as taught in most English-speaking countries. Six-continent conventions either merge "
            "the Americas into one 'America' (common in Latin America and much of Europe) or merge Europe "
            "and Asia into 'Eurasia'; those merged groups are not separate entries here. Countries and "
            "territories are assigned as in the UN M49 regions, so transcontinental countries follow M49: RU "
            "in Europe; TR, CY, GE, AM, AZ in Asia; KZ in Asia; EG in Africa. Same membership as the M49 "
            "region Africa, including territories (EH, IO, RE, SH, TF, YT)."
        ),
    },
    "geo:antarctica": {
        "name": "Antarctica",
        "aliases": (),
        "kind": "continent",
        "members": ("AQ",),
        "source": "convention",
        "notes": (
            "Seven-continent convention (Africa, Antarctica, Asia, Europe, North America, Oceania, South "
            "America), as taught in most English-speaking countries. Six-continent conventions either merge "
            "the Americas into one 'America' (common in Latin America and much of Europe) or merge Europe "
            "and Asia into 'Eurasia'; those merged groups are not separate entries here. Countries and "
            "territories are assigned as in the UN M49 regions, so transcontinental countries follow M49: RU "
            "in Europe; TR, CY, GE, AM, AZ in Asia; KZ in Asia; EG in Africa. Only AQ: sub-Antarctic "
            "territories (BV, GS, HM, TF) stay with the M49 region M49 assigns them to."
        ),
    },
    "geo:asia": {
        "name": "Asia",
        "aliases": ("Asian continent",),
        "kind": "continent",
        "members": (
            "AE", "AF", "AM", "AZ", "BD", "BH", "BN", "BT", "CN", "CY", "GE", "HK", "ID", "IL", "IN", "IQ",
            "IR", "JO", "JP", "KG", "KH", "KP", "KR", "KW", "KZ", "LA", "LB", "LK", "MM", "MN", "MO", "MV",
            "MY", "NP", "OM", "PH", "PK", "PS", "QA", "SA", "SG", "SY", "TH", "TJ", "TL", "TM", "TR", "TW",
            "UZ", "VN", "YE",
        ),
        "source": "convention",
        "notes": (
            "Seven-continent convention (Africa, Antarctica, Asia, Europe, North America, Oceania, South "
            "America), as taught in most English-speaking countries. Six-continent conventions either merge "
            "the Americas into one 'America' (common in Latin America and much of Europe) or merge Europe "
            "and Asia into 'Eurasia'; those merged groups are not separate entries here. Countries and "
            "territories are assigned as in the UN M49 regions, so transcontinental countries follow M49: RU "
            "in Europe; TR, CY, GE, AM, AZ in Asia; KZ in Asia; EG in Africa. The M49 region Asia plus TW, "
            "which the M49 table does not list separately."
        ),
    },
    "geo:europe": {
        "name": "Europe",
        "aliases": ("European continent", "EUR"),
        "kind": "continent",
        "members": (
            "AD", "AL", "AT", "AX", "BA", "BE", "BG", "BY", "CH", "CZ", "DE", "DK", "EE", "ES", "FI", "FO",
            "FR", "GB", "GG", "GI", "GR", "HR", "HU", "IE", "IM", "IS", "IT", "JE", "LI", "LT", "LU", "LV",
            "MC", "MD", "ME", "MK", "MT", "NL", "NO", "PL", "PT", "RO", "RS", "RU", "SE", "SI", "SJ", "SK",
            "SM", "UA", "VA",
        ),
        "source": "convention",
        "notes": (
            "Seven-continent convention (Africa, Antarctica, Asia, Europe, North America, Oceania, South "
            "America), as taught in most English-speaking countries. Six-continent conventions either merge "
            "the Americas into one 'America' (common in Latin America and much of Europe) or merge Europe "
            "and Asia into 'Eurasia'; those merged groups are not separate entries here. Countries and "
            "territories are assigned as in the UN M49 regions, so transcontinental countries follow M49: RU "
            "in Europe; TR, CY, GE, AM, AZ in Asia; KZ in Asia; EG in Africa. Same membership as the M49 "
            "region Europe, so RU is included and TR, CY and the South Caucasus are not."
        ),
    },
    "geo:north-america": {
        "name": "North America",
        "aliases": ("North American continent",),
        "kind": "continent",
        "members": (
            "AG", "AI", "AW", "BB", "BL", "BM", "BQ", "BS", "BZ", "CA", "CR", "CU", "CW", "DM", "DO", "GD",
            "GL", "GP", "GT", "HN", "HT", "JM", "KN", "KY", "LC", "MF", "MQ", "MS", "MX", "NI", "PA", "PM",
            "PR", "SV", "SX", "TC", "TT", "US", "VC", "VG", "VI",
        ),
        "source": "convention",
        "notes": (
            "Seven-continent convention (Africa, Antarctica, Asia, Europe, North America, Oceania, South "
            "America), as taught in most English-speaking countries. Six-continent conventions either merge "
            "the Americas into one 'America' (common in Latin America and much of Europe) or merge Europe "
            "and Asia into 'Eurasia'; those merged groups are not separate entries here. Countries and "
            "territories are assigned as in the UN M49 regions, so transcontinental countries follow M49: RU "
            "in Europe; TR, CY, GE, AM, AZ in Asia; KZ in Asia; EG in Africa. The M49 subregion Northern "
            "America plus the M49 intermediate regions Central America (with MX) and the Caribbean. In "
            "everyday and business use 'North America' often means only US and CA: that group is "
            "geo:us-canada (and geo:namer for the business region)."
        ),
    },
    "geo:south-america": {
        "name": "South America",
        "aliases": ("South American continent",),
        "kind": "continent",
        "members": (
            "AR", "BO", "BR", "BV", "CL", "CO", "EC", "FK", "GF", "GS", "GY", "PE", "PY", "SR", "UY", "VE",
        ),
        "source": "convention",
        "notes": (
            "Seven-continent convention (Africa, Antarctica, Asia, Europe, North America, Oceania, South "
            "America), as taught in most English-speaking countries. Six-continent conventions either merge "
            "the Americas into one 'America' (common in Latin America and much of Europe) or merge Europe "
            "and Asia into 'Eurasia'; those merged groups are not separate entries here. Countries and "
            "territories are assigned as in the UN M49 regions, so transcontinental countries follow M49: RU "
            "in Europe; TR, CY, GE, AM, AZ in Asia; KZ in Asia; EG in Africa. Same membership as the M49 "
            "intermediate region South America (including FK, GF, GS, BV)."
        ),
    },
    "geo:oceania": {
        "name": "Oceania",
        "aliases": ("Australia and Oceania", "Australia/Oceania"),
        "kind": "continent",
        "members": (
            "AS", "AU", "CC", "CK", "CX", "FJ", "FM", "GU", "HM", "KI", "MH", "MP", "NC", "NF", "NR", "NU",
            "NZ", "PF", "PG", "PN", "PW", "SB", "TK", "TO", "TV", "UM", "VU", "WF", "WS",
        ),
        "source": "convention",
        "notes": (
            "Seven-continent convention (Africa, Antarctica, Asia, Europe, North America, Oceania, South "
            "America), as taught in most English-speaking countries. Six-continent conventions either merge "
            "the Americas into one 'America' (common in Latin America and much of Europe) or merge Europe "
            "and Asia into 'Eurasia'; those merged groups are not separate entries here. Countries and "
            "territories are assigned as in the UN M49 regions, so transcontinental countries follow M49: RU "
            "in Europe; TR, CY, GE, AM, AZ in Asia; KZ in Asia; EG in Africa. Same membership as the M49 "
            "region Oceania. Also called 'Australia' as a continent in some conventions, where it means the "
            "continental landmass rather than this wider region."
        ),
    },
    "geo:m49-africa": {
        "name": "Africa (UN M49)",
        "aliases": ("Africa (M49)",),
        "kind": "un-m49-region",
        "members": (
            "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV", "DJ", "DZ", "EG", "EH", "ER",
            "ET", "GA", "GH", "GM", "GN", "GQ", "GW", "IO", "KE", "KM", "LR", "LS", "LY", "MA", "MG", "ML",
            "MR", "MU", "MW", "MZ", "NA", "NE", "NG", "RE", "RW", "SC", "SD", "SH", "SL", "SN", "SO", "SS",
            "ST", "SZ", "TD", "TF", "TG", "TN", "TZ", "UG", "YT", "ZA", "ZM", "ZW",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 region 002. The UN M49 standard is for statistical use and implies no assumption about "
            "political or other affiliation."
        ),
    },
    "geo:m49-americas": {
        "name": "Americas (UN M49)",
        "aliases": ("Americas", "The Americas", "AMER"),
        "kind": "un-m49-region",
        "members": (
            "AG", "AI", "AR", "AW", "BB", "BL", "BM", "BO", "BQ", "BR", "BS", "BV", "BZ", "CA", "CL", "CO",
            "CR", "CU", "CW", "DM", "DO", "EC", "FK", "GD", "GF", "GL", "GP", "GS", "GT", "GY", "HN", "HT",
            "JM", "KN", "KY", "LC", "MF", "MQ", "MS", "MX", "NI", "PA", "PE", "PM", "PR", "PY", "SR", "SV",
            "SX", "TC", "TT", "US", "UY", "VC", "VE", "VG", "VI",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 region 019. The UN M49 standard is for statistical use and implies no assumption about "
            "political or other affiliation."
        ),
    },
    "geo:m49-asia": {
        "name": "Asia (UN M49)",
        "aliases": ("Asia (M49)",),
        "kind": "un-m49-region",
        "members": (
            "AE", "AF", "AM", "AZ", "BD", "BH", "BN", "BT", "CN", "CY", "GE", "HK", "ID", "IL", "IN", "IQ",
            "IR", "JO", "JP", "KG", "KH", "KP", "KR", "KW", "KZ", "LA", "LB", "LK", "MM", "MN", "MO", "MV",
            "MY", "NP", "OM", "PH", "PK", "PS", "QA", "SA", "SG", "SY", "TH", "TJ", "TL", "TM", "TR", "UZ",
            "VN", "YE",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 region 142. The UN M49 standard is for statistical use and implies no assumption about "
            "political or other affiliation."
        ),
    },
    "geo:m49-europe": {
        "name": "Europe (UN M49)",
        "aliases": ("Europe (M49)",),
        "kind": "un-m49-region",
        "members": (
            "AD", "AL", "AT", "AX", "BA", "BE", "BG", "BY", "CH", "CZ", "DE", "DK", "EE", "ES", "FI", "FO",
            "FR", "GB", "GG", "GI", "GR", "HR", "HU", "IE", "IM", "IS", "IT", "JE", "LI", "LT", "LU", "LV",
            "MC", "MD", "ME", "MK", "MT", "NL", "NO", "PL", "PT", "RO", "RS", "RU", "SE", "SI", "SJ", "SK",
            "SM", "UA", "VA",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 region 150. The UN M49 standard is for statistical use and implies no assumption about "
            "political or other affiliation."
        ),
    },
    "geo:m49-oceania": {
        "name": "Oceania (UN M49)",
        "aliases": ("Oceania (M49)",),
        "kind": "un-m49-region",
        "members": (
            "AS", "AU", "CC", "CK", "CX", "FJ", "FM", "GU", "HM", "KI", "MH", "MP", "NC", "NF", "NR", "NU",
            "NZ", "PF", "PG", "PN", "PW", "SB", "TK", "TO", "TV", "UM", "VU", "WF", "WS",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 region 009. The UN M49 standard is for statistical use and implies no assumption about "
            "political or other affiliation. AQ belongs to no M49 region."
        ),
    },
    "geo:m49-australia-new-zealand": {
        "name": "Australia and New Zealand (UN M49)",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("AU", "CC", "CX", "HM", "NF", "NZ"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 053 of Oceania. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:central-asia": {
        "name": "Central Asia",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("KG", "KZ", "TJ", "TM", "UZ"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 143 of Asia. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:eastern-asia": {
        "name": "Eastern Asia",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("CN", "HK", "JP", "KP", "KR", "MN", "MO"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 030 of Asia. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:eastern-europe": {
        "name": "Eastern Europe",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("BG", "BY", "CZ", "HU", "MD", "PL", "RO", "RU", "SK", "UA"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 151 of Europe. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:latin-america-caribbean": {
        "name": "Latin America and the Caribbean",
        "aliases": ("LAC",),
        "kind": "un-m49-subregion",
        "members": (
            "AG", "AI", "AR", "AW", "BB", "BL", "BO", "BQ", "BR", "BS", "BV", "BZ", "CL", "CO", "CR", "CU",
            "CW", "DM", "DO", "EC", "FK", "GD", "GF", "GP", "GS", "GT", "GY", "HN", "HT", "JM", "KN", "KY",
            "LC", "MF", "MQ", "MS", "MX", "NI", "PA", "PE", "PR", "PY", "SR", "SV", "SX", "TC", "TT", "UY",
            "VC", "VE", "VG", "VI",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 419 of Americas. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:melanesia": {
        "name": "Melanesia",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("FJ", "NC", "PG", "SB", "VU"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 054 of Oceania. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:micronesia": {
        "name": "Micronesia",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("FM", "GU", "KI", "MH", "MP", "NR", "PW", "UM"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 057 of Oceania. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation. The region, not the country FM (Federated "
            "States of Micronesia)."
        ),
    },
    "geo:northern-africa": {
        "name": "Northern Africa",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("DZ", "EG", "EH", "LY", "MA", "SD", "TN"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 015 of Africa. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:northern-america": {
        "name": "Northern America",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("BM", "CA", "GL", "PM", "US"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 021 of Americas. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:northern-europe": {
        "name": "Northern Europe",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": (
            "AX", "DK", "EE", "FI", "FO", "GB", "GG", "IE", "IM", "IS", "JE", "LT", "LV", "NO", "SE", "SJ",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 154 of Europe. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:polynesia": {
        "name": "Polynesia",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("AS", "CK", "NU", "PF", "PN", "TK", "TO", "TV", "WF", "WS"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 061 of Oceania. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:south-eastern-asia": {
        "name": "South-eastern Asia",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("BN", "ID", "KH", "LA", "MM", "MY", "PH", "SG", "TH", "TL", "VN"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 035 of Asia. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:southern-asia": {
        "name": "Southern Asia",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("AF", "BD", "BT", "IN", "IR", "LK", "MV", "NP", "PK"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 034 of Asia. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:southern-europe": {
        "name": "Southern Europe",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": (
            "AD", "AL", "BA", "ES", "GI", "GR", "HR", "IT", "ME", "MK", "MT", "PT", "RS", "SI", "SM", "VA",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 039 of Europe. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:sub-saharan-africa": {
        "name": "Sub-Saharan Africa",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": (
            "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV", "DJ", "ER", "ET", "GA", "GH",
            "GM", "GN", "GQ", "GW", "IO", "KE", "KM", "LR", "LS", "MG", "ML", "MR", "MU", "MW", "MZ", "NA",
            "NE", "NG", "RE", "RW", "SC", "SH", "SL", "SN", "SO", "SS", "ST", "SZ", "TD", "TF", "TG", "TZ",
            "UG", "YT", "ZA", "ZM", "ZW",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 202 of Africa. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:western-asia": {
        "name": "Western Asia",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": (
            "AE", "AM", "AZ", "BH", "CY", "GE", "IL", "IQ", "JO", "KW", "LB", "OM", "PS", "QA", "SA", "SY",
            "TR", "YE",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 145 of Asia. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:western-europe": {
        "name": "Western Europe",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("AT", "BE", "CH", "DE", "FR", "LI", "LU", "MC", "NL"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 sub-region 155 of Europe. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:m49-caribbean": {
        "name": "Caribbean (UN M49)",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": (
            "AG", "AI", "AW", "BB", "BL", "BQ", "BS", "CU", "CW", "DM", "DO", "GD", "GP", "HT", "JM", "KN",
            "KY", "LC", "MF", "MQ", "MS", "PR", "SX", "TC", "TT", "VC", "VG", "VI",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 intermediate region 029 within the sub-region Latin America and the Caribbean; listed "
            "with kind un-m49-subregion. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:central-america": {
        "name": "Central America",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("BZ", "CR", "GT", "HN", "MX", "NI", "PA", "SV"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 intermediate region 013 within the sub-region Latin America and the Caribbean; listed "
            "with kind un-m49-subregion. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:eastern-africa": {
        "name": "Eastern Africa",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": (
            "BI", "DJ", "ER", "ET", "IO", "KE", "KM", "MG", "MU", "MW", "MZ", "RE", "RW", "SC", "SO", "SS",
            "TF", "TZ", "UG", "YT", "ZM", "ZW",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 intermediate region 014 within the sub-region Sub-Saharan Africa; listed with kind "
            "un-m49-subregion. The UN M49 standard is for statistical use and implies no assumption about "
            "political or other affiliation."
        ),
    },
    "geo:middle-africa": {
        "name": "Middle Africa",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("AO", "CD", "CF", "CG", "CM", "GA", "GQ", "ST", "TD"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 intermediate region 017 within the sub-region Sub-Saharan Africa; listed with kind "
            "un-m49-subregion. The UN M49 standard is for statistical use and implies no assumption about "
            "political or other affiliation."
        ),
    },
    "geo:m49-south-america": {
        "name": "South America (UN M49)",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": (
            "AR", "BO", "BR", "BV", "CL", "CO", "EC", "FK", "GF", "GS", "GY", "PE", "PY", "SR", "UY", "VE",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 intermediate region 005 within the sub-region Latin America and the Caribbean; listed "
            "with kind un-m49-subregion. The UN M49 standard is for statistical use and implies no "
            "assumption about political or other affiliation."
        ),
    },
    "geo:southern-africa": {
        "name": "Southern Africa",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": ("BW", "LS", "NA", "SZ", "ZA"),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 intermediate region 018 within the sub-region Sub-Saharan Africa; listed with kind "
            "un-m49-subregion. The UN M49 standard is for statistical use and implies no assumption about "
            "political or other affiliation."
        ),
    },
    "geo:western-africa": {
        "name": "Western Africa",
        "aliases": (),
        "kind": "un-m49-subregion",
        "members": (
            "BF", "BJ", "CI", "CV", "GH", "GM", "GN", "GW", "LR", "ML", "MR", "NE", "NG", "SH", "SL", "SN",
            "TG",
        ),
        "source": "https://unstats.un.org/unsd/methodology/m49/overview/",
        "notes": (
            "UN M49 intermediate region 011 within the sub-region Sub-Saharan Africa; listed with kind "
            "un-m49-subregion. The UN M49 standard is for statistical use and implies no assumption about "
            "political or other affiliation."
        ),
    },
    "geo:us-canada": {
        "name": "US & Canada",
        "aliases": (
            "US and Canada", "USA & Canada", "USA and Canada", "US/Canada", "U.S. & Canada", "Canada & US",
            "Canada and the US", "North America (US & Canada)",
        ),
        "kind": "custom",
        "members": ("CA", "US"),
        "source": "convention",
        "notes": (
            "Exactly the United States and Canada, as postings mean by 'US & Canada' or 'North America (US & "
            "Canada)'. Distinct from the M49 sub-region Northern America (which adds BM, GL, PM) and from "
            "the continent North America (which adds MX, Central America and the Caribbean); the bare name "
            "'North America' belongs to the continent."
        ),
    },
    "geo:us-canada-mexico": {
        "name": "US, Canada & Mexico",
        "aliases": ("US and Canada and Mexico",),
        "kind": "custom",
        "members": ("CA", "MX", "US"),
        "source": "convention",
        "notes": (
            "The United States, Canada and Mexico, as postings mean by 'US and Canada and Mexico': the same "
            "three countries as the CUSMA / USMCA / T-MEC trade agreement (legal:cusma). Narrower than the "
            "continent North America (geo:north-america), wider than US & Canada (geo:us-canada)."
        ),
    },
    "geo:world": {
        "name": "World",
        "aliases": ("Worldwide", "Global", "Anywhere", "International", "Any Location", "Everywhere"),
        "kind": "custom",
        "members": (
            "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT", "AU", "AW", "AX", "AZ",
            "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS",
            "BT", "BV", "BW", "BY", "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN",
            "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM", "DO", "DZ", "EC", "EE",
            "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK", "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF",
            "GG", "GH", "GI", "GL", "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM",
            "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR", "IS", "IT", "JE", "JM",
            "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN", "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC",
            "LI", "LK", "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK",
            "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW", "MX", "MY", "MZ", "NA",
            "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP", "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG",
            "PH", "PK", "PL", "PM", "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW",
            "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM", "SN", "SO", "SR", "SS",
            "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF", "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO",
            "TR", "TT", "TV", "TW", "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
            "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
        ),
        "source": "convention",
        "notes": (
            "Every country and territory: all 249 assigned ISO 3166-1 alpha-2 codes, the package's full ISO "
            "table. Means no geographic limit, as location strings mean by 'Remote - Worldwide' or "
            "'Anywhere'."
        ),
    },
    "geo:nordic": {
        "name": "Nordic countries",
        "aliases": ("Nordics", "Nordic region", "Nordic", "Norden"),
        "kind": "custom",
        "members": ("AX", "DK", "FI", "FO", "GL", "IS", "NO", "SE"),
        "source": "convention",
        "notes": (
            "The five Nordic states (DK, FI, IS, NO, SE) and the three autonomous areas that take part in "
            "Nordic co-operation (AX, FO, GL). SJ (Svalbard and Jan Mayen, part of Norway) is not listed "
            "separately. Wider than Scandinavia."
        ),
    },
    "geo:scandinavia": {
        "name": "Scandinavia",
        "aliases": ("Scandinavian countries",),
        "kind": "custom",
        "members": ("DK", "NO", "SE"),
        "source": "convention",
        "notes": (
            "Strict sense: Denmark, Norway and Sweden. In looser use 'Scandinavia' also takes in FI and IS, "
            "which is the Nordic countries group (geo:nordic)."
        ),
    },
    "geo:benelux": {
        "name": "Benelux",
        "aliases": ("Benelux countries", "Low Countries"),
        "kind": "custom",
        "members": ("BE", "LU", "NL"),
        "source": "convention",
        "notes": "Belgium, the Netherlands and Luxembourg; also the name of their Benelux Union.",
    },
    "geo:iberia": {
        "name": "Iberia",
        "aliases": ("Iberian Peninsula",),
        "kind": "custom",
        "members": ("AD", "ES", "GI", "PT"),
        "source": "convention",
        "notes": (
            "The countries and territories of the Iberian Peninsula: ES, PT, AD and GI. In business use "
            "'Iberia' usually means Spain and Portugal only."
        ),
    },
    "geo:british-isles": {
        "name": "British Isles",
        "aliases": ("Britain and Ireland", "Britain & Ireland"),
        "kind": "custom",
        "members": ("GB", "GG", "IE", "IM", "JE"),
        "source": "convention",
        "notes": (
            "A geographic term for the archipelago: GB, IE and the Crown Dependencies IM, JE, GG. The term "
            "is sensitive, notably in Ireland, and is not a political grouping; 'Britain and Ireland' is a "
            "common alternative. Not the same as 'UK & Ireland' (GB and IE only)."
        ),
    },
    "geo:baltics": {
        "name": "Baltics",
        "aliases": ("Baltic states", "Baltic countries", "Baltic"),
        "kind": "custom",
        "members": ("EE", "LT", "LV"),
        "source": "convention",
        "notes": "Estonia, Latvia and Lithuania.",
    },
    "geo:balkans": {
        "name": "Balkans",
        "aliases": ("The Balkans", "Balkan Peninsula", "Balkan countries"),
        "kind": "custom",
        "members": ("AL", "BA", "BG", "GR", "HR", "ME", "MK", "RO", "RS", "SI"),
        "source": "convention",
        "notes": (
            "The edges are fuzzy. Listed: the commonest broad set of countries wholly or largely on the "
            "Balkan Peninsula, AL, BA, BG, GR, HR, ME, MK, RO, RS, SI. SI, HR, RO and GR are left out by "
            "some definitions; TR (East Thrace) is added by others. Kosovo is included in most definitions "
            "but has no ISO 3166-1 code (XK is a user-assigned code), so it cannot be listed here."
        ),
    },
    "geo:dach": {
        "name": "DACH",
        "aliases": ("D-A-CH", "DACH region"),
        "kind": "custom",
        "members": ("AT", "CH", "DE"),
        "source": "convention",
        "notes": (
            "Germany (D), Austria (A) and Switzerland (CH), the main German-speaking countries. Some uses "
            "add LI ('DACHL')."
        ),
    },
    "geo:caribbean": {
        "name": "Caribbean",
        "aliases": ("Caribbean islands", "West Indies", "The Caribbean"),
        "kind": "custom",
        "members": (
            "AG", "AI", "AW", "BB", "BL", "BQ", "BS", "CU", "CW", "DM", "DO", "GD", "GP", "HT", "JM", "KN",
            "KY", "LC", "MF", "MQ", "MS", "PR", "SX", "TC", "TT", "VC", "VG", "VI",
        ),
        "source": "convention",
        "notes": (
            "The Caribbean islands, same membership as the M49 intermediate region Caribbean. Wider uses "
            "(the Caribbean basin, CARICOM) also take in BZ, GY and SR on the mainland."
        ),
    },
    "geo:middle-east": {
        "name": "Middle East",
        "aliases": ("Mideast", "The Middle East"),
        "kind": "custom",
        "members": (
            "AE", "BH", "CY", "EG", "IL", "IQ", "IR", "JO", "KW", "LB", "OM", "PS", "QA", "SA", "SY", "TR",
            "YE",
        ),
        "source": "convention",
        "notes": (
            "Definitions vary. Listed: the commonest modern set, the Arabian Peninsula and Levant states "
            "with EG, IR, IQ, TR and CY. Some definitions add the Maghreb (see geo:mena), the South "
            "Caucasus, AF or PK, or leave out CY, EG or TR."
        ),
    },
    "geo:southeast-asia": {
        "name": "Southeast Asia",
        "aliases": ("South East Asia", "South-East Asia", "SE Asia"),
        "kind": "custom",
        "members": ("BN", "ID", "KH", "LA", "MM", "MY", "PH", "SG", "TH", "TL", "VN"),
        "source": "convention",
        "notes": "Same membership as the M49 sub-region South-eastern Asia (the eleven ASEAN members).",
    },
    "geo:emea": {
        "name": "EMEA",
        "aliases": (
            "Europe, Middle East and Africa", "Europe, the Middle East and Africa",
            "Europe Middle East Africa",
        ),
        "kind": "business",
        "members": (
            "AD", "AE", "AL", "AM", "AO", "AT", "AX", "AZ", "BA", "BE", "BF", "BG", "BH", "BI", "BJ", "BW",
            "BY", "CD", "CF", "CG", "CH", "CI", "CM", "CV", "CY", "CZ", "DE", "DJ", "DK", "DZ", "EE", "EG",
            "EH", "ER", "ES", "ET", "FI", "FO", "FR", "GA", "GB", "GE", "GG", "GH", "GI", "GM", "GN", "GQ",
            "GR", "GW", "HR", "HU", "IE", "IL", "IM", "IO", "IQ", "IR", "IS", "IT", "JE", "JO", "KE", "KM",
            "KW", "LB", "LI", "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MG", "MK", "ML",
            "MR", "MT", "MU", "MW", "MZ", "NA", "NE", "NG", "NL", "NO", "OM", "PL", "PS", "PT", "QA", "RE",
            "RO", "RS", "RU", "RW", "SA", "SC", "SD", "SE", "SH", "SI", "SJ", "SK", "SL", "SM", "SN", "SO",
            "SS", "ST", "SY", "SZ", "TD", "TF", "TG", "TN", "TR", "TZ", "UA", "UG", "VA", "YE", "YT", "ZA",
            "ZM", "ZW",
        ),
        "source": "convention",
        "notes": (
            "Business region: the membership is a convention, not an official definition, and varies between "
            "organisations; this is the commonest definition. Europe, the Middle East and Africa: the M49 "
            "regions Europe and Africa, the M49 sub-region Western Asia (which includes TR, CY and the South "
            "Caucasus) and IR. Central Asia is sometimes added."
        ),
    },
    "geo:apac": {
        "name": "APAC",
        "aliases": ("Asia-Pacific", "Asia Pacific", "Asia/Pacific", "AsiaPac", "Asia Pac"),
        "kind": "business",
        "members": (
            "AS", "AU", "BD", "BN", "BT", "CC", "CK", "CN", "CX", "FJ", "FM", "GU", "HK", "HM", "ID", "IN",
            "JP", "KH", "KI", "KP", "KR", "LA", "LK", "MH", "MM", "MN", "MO", "MP", "MV", "MY", "NC", "NF",
            "NP", "NR", "NU", "NZ", "PF", "PG", "PH", "PK", "PN", "PW", "SB", "SG", "TH", "TK", "TL", "TO",
            "TV", "TW", "UM", "VN", "VU", "WF", "WS",
        ),
        "source": "convention",
        "notes": (
            "Business region: the membership is a convention, not an official definition, and varies between "
            "organisations; this is the commonest definition. Asia-Pacific: East Asia (with TW), Southeast "
            "Asia, South Asia without AF and IR (usually counted in the Middle East or EMEA) and Oceania. "
            "Central Asia is usually left out; some uses also leave out South Asia or Oceania, or count "
            "Australia and New Zealand separately (geo:anz)."
        ),
    },
    "geo:latam": {
        "name": "LATAM",
        "aliases": ("Latin America", "LatAm region"),
        "kind": "business",
        "members": (
            "AG", "AI", "AR", "AW", "BB", "BL", "BO", "BQ", "BR", "BS", "BV", "BZ", "CL", "CO", "CR", "CU",
            "CW", "DM", "DO", "EC", "FK", "GD", "GF", "GP", "GS", "GT", "GY", "HN", "HT", "JM", "KN", "KY",
            "LC", "MF", "MQ", "MS", "MX", "NI", "PA", "PE", "PR", "PY", "SR", "SV", "SX", "TC", "TT", "UY",
            "VC", "VE", "VG", "VI",
        ),
        "source": "convention",
        "notes": (
            "Business region: the membership is a convention, not an official definition, and varies between "
            "organisations; this is the commonest definition. Latin America: the same set as the M49 "
            "sub-region Latin America and the Caribbean (MX, Central and South America and the Caribbean). "
            "Some uses leave out the non-Spanish- and non-Portuguese-speaking Caribbean."
        ),
    },
    "geo:namer": {
        "name": "NA / NAMER",
        "aliases": ("NAMER", "NORAM", "North America (business region)"),
        "kind": "business",
        "members": ("CA", "US"),
        "source": "convention",
        "notes": (
            "Business region: the membership is a convention, not an official definition, and varies between "
            "organisations; this is the commonest definition. North America in sales and hiring regions: US "
            "and CA, with MX usually counted in LATAM. The bare abbreviation 'NA' is not an alias because it "
            "is also Namibia's ISO code and a common 'not applicable' marker."
        ),
    },
    "geo:anz": {
        "name": "ANZ",
        "aliases": ("Australia and New Zealand", "Australia & New Zealand", "A/NZ"),
        "kind": "business",
        "members": ("AU", "NZ"),
        "source": "convention",
        "notes": (
            "Business region: the membership is a convention, not an official definition, and varies between "
            "organisations; this is the commonest definition. Australia and New Zealand. Narrower than the "
            "M49 sub-region Australia and New Zealand, which also has the Australian external territories "
            "CC, CX, HM and NF."
        ),
    },
    "geo:mena": {
        "name": "MENA",
        "aliases": ("Middle East and North Africa", "Middle East & North Africa"),
        "kind": "business",
        "members": (
            "AE", "BH", "DZ", "EG", "IL", "IQ", "IR", "JO", "KW", "LB", "LY", "MA", "OM", "PS", "QA", "SA",
            "SY", "TN", "YE",
        ),
        "source": "convention",
        "notes": (
            "Business region: the membership is a convention, not an official definition, and varies between "
            "organisations; this is the commonest definition. The Middle East and North Africa: the Middle "
            "East without CY and TR, plus DZ, LY, MA and TN (EG is already in). Some uses add SD, MR, DJ or "
            "EH, or keep TR."
        ),
    },
}

# id -> {name, aliases, kind, members, source, notes}; each member has code (alpha-2, or None for
# a member without one, which then has `group` (an id here) or `entity` (a name)), since and
# until (None when unknown or still a member), and suspended_since when the organisation has
# suspended it
LEGAL = {
    "legal:eu": {
        "name": "European Union",
        "aliases": ("EU",),
        "kind": "union",
        "members": (
            {"code": "BE", "since": "1958-01-01", "until": None},
            {"code": "DE", "since": "1958-01-01", "until": None},
            {"code": "FR", "since": "1958-01-01", "until": None},
            {"code": "IT", "since": "1958-01-01", "until": None},
            {"code": "LU", "since": "1958-01-01", "until": None},
            {"code": "NL", "since": "1958-01-01", "until": None},
            {"code": "DK", "since": "1973-01-01", "until": None},
            {"code": "IE", "since": "1973-01-01", "until": None},
            {"code": "GB", "since": "1973-01-01", "until": "2020-01-31"},
            {"code": "GR", "since": "1981-01-01", "until": None},
            {"code": "ES", "since": "1986-01-01", "until": None},
            {"code": "PT", "since": "1986-01-01", "until": None},
            {"code": "AT", "since": "1995-01-01", "until": None},
            {"code": "FI", "since": "1995-01-01", "until": None},
            {"code": "SE", "since": "1995-01-01", "until": None},
            {"code": "CY", "since": "2004-05-01", "until": None},
            {"code": "CZ", "since": "2004-05-01", "until": None},
            {"code": "EE", "since": "2004-05-01", "until": None},
            {"code": "HU", "since": "2004-05-01", "until": None},
            {"code": "LV", "since": "2004-05-01", "until": None},
            {"code": "LT", "since": "2004-05-01", "until": None},
            {"code": "MT", "since": "2004-05-01", "until": None},
            {"code": "PL", "since": "2004-05-01", "until": None},
            {"code": "SK", "since": "2004-05-01", "until": None},
            {"code": "SI", "since": "2004-05-01", "until": None},
            {"code": "BG", "since": "2007-01-01", "until": None},
            {"code": "RO", "since": "2007-01-01", "until": None},
            {"code": "HR", "since": "2013-07-01", "until": None},
        ),
        "source": "https://european-union.europa.eu/principles-countries-history/eu-countries_en",
        "notes": (
            "27 member states. 'since' is the date of joining the European Communities, which became the EU "
            "on 1993-11-01; the six founders' date is the entry into force of the EEC Treaty. GB left on "
            "2020-01-31 (its last day as a member state). Members are states; some of their territories with "
            "their own ISO codes are part of the EU (outermost regions such as GF, GP, MQ, RE, YT, MF; and "
            "AX), others are not (e.g. GL, FO, and most overseas countries and territories). Greenland, part "
            "of DK, left the European Communities in 1985."
        ),
    },
    "legal:eurozone": {
        "name": "Euro area",
        "aliases": ("Eurozone", "Euro zone", "Euro-zone"),
        "kind": "currency-union",
        "members": (
            {"code": "AT", "since": "1999-01-01", "until": None},
            {"code": "BE", "since": "1999-01-01", "until": None},
            {"code": "DE", "since": "1999-01-01", "until": None},
            {"code": "ES", "since": "1999-01-01", "until": None},
            {"code": "FI", "since": "1999-01-01", "until": None},
            {"code": "FR", "since": "1999-01-01", "until": None},
            {"code": "IE", "since": "1999-01-01", "until": None},
            {"code": "IT", "since": "1999-01-01", "until": None},
            {"code": "LU", "since": "1999-01-01", "until": None},
            {"code": "NL", "since": "1999-01-01", "until": None},
            {"code": "PT", "since": "1999-01-01", "until": None},
            {"code": "GR", "since": "2001-01-01", "until": None},
            {"code": "SI", "since": "2007-01-01", "until": None},
            {"code": "CY", "since": "2008-01-01", "until": None},
            {"code": "MT", "since": "2008-01-01", "until": None},
            {"code": "SK", "since": "2009-01-01", "until": None},
            {"code": "EE", "since": "2011-01-01", "until": None},
            {"code": "LV", "since": "2014-01-01", "until": None},
            {"code": "LT", "since": "2015-01-01", "until": None},
            {"code": "HR", "since": "2023-01-01", "until": None},
            {"code": "BG", "since": "2026-01-01", "until": None},
        ),
        "source": "https://www.ecb.europa.eu/euro/intro/html/index.en.html",
        "notes": (
            "The 21 EU member states that use the euro, per the ECB (BG joined on 2026-01-01). Not every EU "
            "member: the others are outside the euro area. AD, MC, SM and VA use the euro under monetary "
            "agreements with the EU, and ME and Kosovo use it unilaterally; none of them is a euro area "
            "member."
        ),
    },
    "legal:eea": {
        "name": "European Economic Area",
        "aliases": ("EEA",),
        "kind": "treaty-area",
        "members": (
            {"code": "BE", "since": "1994-01-01", "until": None},
            {"code": "DE", "since": "1994-01-01", "until": None},
            {"code": "FR", "since": "1994-01-01", "until": None},
            {"code": "IT", "since": "1994-01-01", "until": None},
            {"code": "LU", "since": "1994-01-01", "until": None},
            {"code": "NL", "since": "1994-01-01", "until": None},
            {"code": "DK", "since": "1994-01-01", "until": None},
            {"code": "IE", "since": "1994-01-01", "until": None},
            {"code": "GR", "since": "1994-01-01", "until": None},
            {"code": "ES", "since": "1994-01-01", "until": None},
            {"code": "PT", "since": "1994-01-01", "until": None},
            {"code": "GB", "since": "1994-01-01", "until": "2020-01-31"},
            {"code": "AT", "since": "1994-01-01", "until": None},
            {"code": "FI", "since": "1994-01-01", "until": None},
            {"code": "SE", "since": "1994-01-01", "until": None},
            {"code": "IS", "since": "1994-01-01", "until": None},
            {"code": "NO", "since": "1994-01-01", "until": None},
            {"code": "LI", "since": "1995-05-01", "until": None},
            {"code": "CY", "since": "2004-05-01", "until": None},
            {"code": "CZ", "since": "2004-05-01", "until": None},
            {"code": "EE", "since": "2004-05-01", "until": None},
            {"code": "HU", "since": "2004-05-01", "until": None},
            {"code": "LV", "since": "2004-05-01", "until": None},
            {"code": "LT", "since": "2004-05-01", "until": None},
            {"code": "MT", "since": "2004-05-01", "until": None},
            {"code": "PL", "since": "2004-05-01", "until": None},
            {"code": "SK", "since": "2004-05-01", "until": None},
            {"code": "SI", "since": "2004-05-01", "until": None},
            {"code": "BG", "since": "2007-08-01", "until": None},
            {"code": "RO", "since": "2007-08-01", "until": None},
            {"code": "HR", "since": "2014-04-12", "until": None},
        ),
        "source": "https://www.efta.int/eea/eea-agreement",
        "notes": (
            "The EU member states plus three EFTA states (IS, LI, NO); CH is in EFTA but not the EEA. The "
            "agreement entered into force on 1994-01-01 (AT, FI, SE took part first as EFTA states, then as "
            "EU members). Dates for the 2004, 2007 and 2013 EU entrants are the start of provisional "
            "application of each EEA enlargement agreement, as published by EFTA (in force 2005-12-06, "
            "2011-11-09 and 2025-02-19). GB ceased to be a party when it left the EU on 2020-01-31; the "
            "agreement still applied to it during the transition period to 2020-12-31."
        ),
    },
    "legal:efta": {
        "name": "European Free Trade Association",
        "aliases": ("EFTA",),
        "kind": "trade-agreement",
        "members": (
            {"code": "CH", "since": "1960", "until": None},
            {"code": "NO", "since": "1960", "until": None},
            {"code": "IS", "since": "1970", "until": None},
            {"code": "LI", "since": "1991", "until": None},
            {"code": "AT", "since": "1960", "until": "1994-12-31"},
            {"code": "DK", "since": "1960", "until": "1972-12-31"},
            {"code": "FI", "since": "1986", "until": "1994-12-31"},
            {"code": "PT", "since": "1960", "until": "1985-12-31"},
            {"code": "SE", "since": "1960", "until": "1994-12-31"},
            {"code": "GB", "since": "1960", "until": "1972-12-31"},
        ),
        "source": "https://www.efta.int/about-efta/history",
        "notes": (
            "Four members: IS, LI, NO, CH. Founded in 1960; years as published by EFTA. FI was an associate "
            "member from 1961 and a full member from 1986. Former members left on joining the European "
            "Communities or the EU (DK and GB on 1973-01-01, PT on 1986-01-01, AT, FI and SE on 1995-01-01); "
            "'until' is their last day."
        ),
    },
    "legal:schengen": {
        "name": "Schengen Area",
        "aliases": ("Schengen", "Schengen zone", "Schengen countries"),
        "kind": "treaty-area",
        "members": (
            {"code": "BE", "since": "1995", "until": None},
            {"code": "DE", "since": "1995", "until": None},
            {"code": "FR", "since": "1995", "until": None},
            {"code": "LU", "since": "1995", "until": None},
            {"code": "NL", "since": "1995", "until": None},
            {"code": "ES", "since": "1995", "until": None},
            {"code": "PT", "since": "1995", "until": None},
            {"code": "IT", "since": "1997", "until": None},
            {"code": "AT", "since": "1997", "until": None},
            {"code": "GR", "since": "2000", "until": None},
            {"code": "DK", "since": "2001", "until": None},
            {"code": "FI", "since": "2001", "until": None},
            {"code": "SE", "since": "2001", "until": None},
            {"code": "NO", "since": "2001", "until": None},
            {"code": "IS", "since": "2001", "until": None},
            {"code": "CZ", "since": "2007", "until": None},
            {"code": "EE", "since": "2007", "until": None},
            {"code": "HU", "since": "2007", "until": None},
            {"code": "LV", "since": "2007", "until": None},
            {"code": "LT", "since": "2007", "until": None},
            {"code": "MT", "since": "2007", "until": None},
            {"code": "PL", "since": "2007", "until": None},
            {"code": "SI", "since": "2007", "until": None},
            {"code": "SK", "since": "2007", "until": None},
            {"code": "CH", "since": "2008", "until": None},
            {"code": "LI", "since": "2011", "until": None},
            {"code": "HR", "since": "2023", "until": None},
            {"code": "BG", "since": "2025-01-01", "until": None},
            {"code": "RO", "since": "2025-01-01", "until": None},
        ),
        "source": "https://home-affairs.ec.europa.eu/policies/schengen/schengen-area_en",
        "notes": (
            "29 countries: 25 EU member states and four non-EU countries (IS, NO, CH, LI). 'since' is the "
            "year internal border controls were abolished, per the European Commission's Schengen timeline; "
            "BG and RO joined fully on 2025-01-01 (air and sea border checks were lifted in 2024). Not "
            "members: IE (opt-out) and CY (applies part of the Schengen rules; internal border controls not "
            "yet lifted). MC, SM and VA have open borders with Schengen neighbours without being members. "
            "Some territories of members are outside the area (e.g. GL, FO, SJ, and the EU outermost "
            "regions)."
        ),
    },
    "legal:canzuk": {
        "name": "CANZUK",
        "aliases": ("CANZUK countries",),
        "kind": "forum",
        "members": (
            {"code": "CA", "since": None, "until": None},
            {"code": "AU", "since": None, "until": None},
            {"code": "NZ", "since": None, "until": None},
            {"code": "GB", "since": None, "until": None},
        ),
        "source": "convention",
        "notes": (
            "Not an organisation or a treaty: an informal proposal for closer co-operation (trade, travel, "
            "foreign policy) among Canada, Australia, New Zealand and the United Kingdom. Membership is the "
            "four countries the name abbreviates; there are no joining dates and no official source. Kind "
            "'forum' is the nearest fit."
        ),
    },
    "legal:five-eyes": {
        "name": "Five Eyes",
        "aliases": ("FVEY", "5 Eyes", "Five Eyes alliance"),
        "kind": "alliance",
        "members": (
            {"code": "AU", "since": None, "until": None},
            {"code": "CA", "since": None, "until": None},
            {"code": "NZ", "since": None, "until": None},
            {"code": "GB", "since": None, "until": None},
            {"code": "US", "since": None, "until": None},
        ),
        "source": "https://www.dni.gov/index.php/who-we-are/organizations/icig/icig-partnerships/icig-fiorc",
        "notes": (
            "Intelligence-sharing arrangement among Australia, Canada, New Zealand, the United Kingdom and "
            "the United States, growing out of the UKUSA Agreement. Source: the Five Eyes Intelligence "
            "Oversight and Review Council page of the US Office of the Director of National Intelligence. "
            "Joining dates are left out: the arrangement grew in stages and no official membership dates are "
            "published."
        ),
    },
    "legal:cusma": {
        "name": "CUSMA / USMCA / T-MEC",
        "aliases": (
            "CUSMA", "USMCA", "T-MEC", "TMEC", "ACEUM", "Canada-United States-Mexico Agreement",
            "United States-Mexico-Canada Agreement",
        ),
        "kind": "trade-agreement",
        "members": (
            {"code": "CA", "since": "2020-07-01", "until": None},
            {"code": "MX", "since": "2020-07-01", "until": None},
            {"code": "US", "since": "2020-07-01", "until": None},
        ),
        "source": "https://www.international.gc.ca/trade-commerce/trade-agreements-accords-commerciaux/agr-acc/cusma-aceum/index.aspx?lang=eng",
        "notes": (
            "The same agreement under its names in Canada (CUSMA, French ACEUM), the United States (USMCA) "
            "and Mexico (T-MEC). In force since 2020-07-01, replacing NAFTA (1994). At the first joint "
            "review on 2026-07-01 the parties did not all confirm a 16-year extension, which starts annual "
            "joint reviews; the agreement remains in force."
        ),
    },
    "legal:asean": {
        "name": "Association of Southeast Asian Nations",
        "aliases": ("ASEAN",),
        "kind": "intergovernmental",
        "members": (
            {"code": "ID", "since": "1967-08-08", "until": None},
            {"code": "MY", "since": "1967-08-08", "until": None},
            {"code": "PH", "since": "1967-08-08", "until": None},
            {"code": "SG", "since": "1967-08-08", "until": None},
            {"code": "TH", "since": "1967-08-08", "until": None},
            {"code": "BN", "since": "1984-01-07", "until": None},
            {"code": "VN", "since": "1995-07-28", "until": None},
            {"code": "LA", "since": "1997-07-23", "until": None},
            {"code": "MM", "since": "1997-07-23", "until": None},
            {"code": "KH", "since": "1999-04-30", "until": None},
            {"code": "TL", "since": "2025-10-26", "until": None},
        ),
        "source": "https://asean.org/member-states/",
        "notes": "Eleven members; TL was admitted as the eleventh on 2025-10-26 at the 47th ASEAN Summit.",
    },
    "legal:gcc": {
        "name": "Gulf Cooperation Council",
        "aliases": ("GCC", "Cooperation Council for the Arab States of the Gulf"),
        "kind": "intergovernmental",
        "members": (
            {"code": "AE", "since": "1981-05-25", "until": None},
            {"code": "BH", "since": "1981-05-25", "until": None},
            {"code": "KW", "since": "1981-05-25", "until": None},
            {"code": "OM", "since": "1981-05-25", "until": None},
            {"code": "QA", "since": "1981-05-25", "until": None},
            {"code": "SA", "since": "1981-05-25", "until": None},
        ),
        "source": "https://gcc-sg.org/en/AboutUs/Pages/default.aspx",
        "notes": "The six founding states; the charter was signed on 1981-05-25.",
    },
    "legal:commonwealth": {
        "name": "Commonwealth of Nations",
        "aliases": ("The Commonwealth", "Commonwealth"),
        "kind": "intergovernmental",
        "members": (
            {"code": "AG", "since": "1981", "until": None},
            {"code": "AU", "since": "1931", "until": None},
            {"code": "BB", "since": "1966", "until": None},
            {"code": "BD", "since": "1972", "until": None},
            {"code": "BN", "since": "1984", "until": None},
            {"code": "BS", "since": "1973", "until": None},
            {"code": "BW", "since": "1966", "until": None},
            {"code": "BZ", "since": "1981", "until": None},
            {"code": "CA", "since": "1931", "until": None},
            {"code": "CM", "since": None, "until": None},
            {"code": "CY", "since": "1961", "until": None},
            {"code": "DM", "since": "1978", "until": None},
            {"code": "FJ", "since": "1970", "until": None},
            {"code": "GA", "since": "2022", "until": None},
            {"code": "GB", "since": "1926", "until": None},
            {"code": "GD", "since": "1974", "until": None},
            {"code": "GH", "since": "1957", "until": None},
            {"code": "GM", "since": "2018", "until": None},
            {"code": "GY", "since": "1966", "until": None},
            {"code": "IN", "since": "1947", "until": None},
            {"code": "JM", "since": "1962", "until": None},
            {"code": "KE", "since": "1963", "until": None},
            {"code": "KI", "since": "1979", "until": None},
            {"code": "KN", "since": "1983", "until": None},
            {"code": "LC", "since": "1979", "until": None},
            {"code": "LK", "since": "1948", "until": None},
            {"code": "LS", "since": "1966", "until": None},
            {"code": "MT", "since": "1964", "until": None},
            {"code": "MU", "since": "1968", "until": None},
            {"code": "MV", "since": "2020-02-01", "until": None},
            {"code": "MW", "since": "1964", "until": None},
            {"code": "MY", "since": "1957", "until": None},
            {"code": "MZ", "since": "1995", "until": None},
            {"code": "NA", "since": "1990", "until": None},
            {"code": "NG", "since": "1960", "until": None},
            {"code": "NR", "since": "1999", "until": None},
            {"code": "NZ", "since": "1931", "until": None},
            {"code": "PG", "since": "1975", "until": None},
            {"code": "PK", "since": "1989", "until": None},
            {"code": "RW", "since": "2009", "until": None},
            {"code": "SB", "since": "1978", "until": None},
            {"code": "SC", "since": "1976", "until": None},
            {"code": "SG", "since": "1965", "until": None},
            {"code": "SL", "since": "1961", "until": None},
            {"code": "SZ", "since": "1968", "until": None},
            {"code": "TG", "since": "2022", "until": None},
            {"code": "TO", "since": "1970", "until": None},
            {"code": "TT", "since": "1962", "until": None},
            {"code": "TV", "since": "1978", "until": None},
            {"code": "TZ", "since": "1961", "until": None},
            {"code": "UG", "since": "1962", "until": None},
            {"code": "VC", "since": "1979", "until": None},
            {"code": "VU", "since": "1980", "until": None},
            {"code": "WS", "since": "1970", "until": None},
            {"code": "ZA", "since": "1994", "until": None},
            {"code": "ZM", "since": "1964", "until": None},
            {"code": "IE", "since": None, "until": "1949"},
            {"code": "ZW", "since": None, "until": "2003"},
        ),
        "source": "https://thecommonwealth.org/our-member-countries",
        "notes": (
            "56 member countries. 'since' is the year each joined (for members that left and rejoined, the "
            "current membership), as published on each Commonwealth Secretariat country page, except where a "
            "member note says otherwise. Former members: IE (left 1949) and ZW (withdrew 2003)."
        ),
    },
    "legal:oecd": {
        "name": "Organisation for Economic Co-operation and Development",
        "aliases": ("OECD", "Organization for Economic Cooperation and Development"),
        "kind": "intergovernmental",
        "members": (
            {"code": "AT", "since": "1961-09-29", "until": None},
            {"code": "AU", "since": "1971-06-07", "until": None},
            {"code": "BE", "since": "1961-09-13", "until": None},
            {"code": "CA", "since": "1961-04-10", "until": None},
            {"code": "CH", "since": "1961-09-28", "until": None},
            {"code": "CL", "since": "2010-05-07", "until": None},
            {"code": "CO", "since": "2020-04-28", "until": None},
            {"code": "CR", "since": "2021-05-25", "until": None},
            {"code": "CZ", "since": "1995-12-21", "until": None},
            {"code": "DE", "since": "1961-09-27", "until": None},
            {"code": "DK", "since": "1961-05-30", "until": None},
            {"code": "EE", "since": "2010-12-09", "until": None},
            {"code": "ES", "since": "1961-08-03", "until": None},
            {"code": "FI", "since": "1969-01-28", "until": None},
            {"code": "FR", "since": "1961-08-07", "until": None},
            {"code": "GB", "since": "1961-05-02", "until": None},
            {"code": "GR", "since": "1961-09-27", "until": None},
            {"code": "HU", "since": "1996-05-07", "until": None},
            {"code": "IE", "since": "1961-08-17", "until": None},
            {"code": "IL", "since": "2010-09-07", "until": None},
            {"code": "IS", "since": "1961-06-05", "until": None},
            {"code": "IT", "since": "1962-03-29", "until": None},
            {"code": "JP", "since": "1964-04-28", "until": None},
            {"code": "KR", "since": "1996-12-12", "until": None},
            {"code": "LT", "since": "2018-07-05", "until": None},
            {"code": "LU", "since": "1961-12-07", "until": None},
            {"code": "LV", "since": "2016-07-01", "until": None},
            {"code": "MX", "since": "1994-05-18", "until": None},
            {"code": "NL", "since": "1961-11-13", "until": None},
            {"code": "NO", "since": "1961-07-04", "until": None},
            {"code": "NZ", "since": "1973-05-29", "until": None},
            {"code": "PL", "since": "1996-11-22", "until": None},
            {"code": "PT", "since": "1961-08-04", "until": None},
            {"code": "SE", "since": "1961-09-28", "until": None},
            {"code": "SI", "since": "2010-07-21", "until": None},
            {"code": "SK", "since": "2000-12-14", "until": None},
            {"code": "TR", "since": "1961-08-02", "until": None},
            {"code": "US", "since": "1961-04-12", "until": None},
        ),
        "source": "https://www.oecd.org/en/about/members-partners.html",
        "notes": (
            "38 member countries. 'since' is the date each deposited its instrument of ratification of the "
            "OECD Convention, as listed by the OECD (and reproduced by Eurostat); the Convention entered "
            "into force on 1961-09-30, so founders' dates before that are ratification, not membership, "
            "dates. Accession candidates are not members."
        ),
    },
    "legal:g7": {
        "name": "Group of Seven",
        "aliases": ("G7", "G-7"),
        "kind": "forum",
        "members": (
            {"code": "FR", "since": "1975", "until": None},
            {"code": "DE", "since": "1975", "until": None},
            {"code": "IT", "since": "1975", "until": None},
            {"code": "JP", "since": "1975", "until": None},
            {"code": "GB", "since": "1975", "until": None},
            {"code": "US", "since": "1975", "until": None},
            {"code": "CA", "since": "1976", "until": None},
            {"code": None, "since": None, "until": None, "group": "legal:eu"},
            {"code": "RU", "since": None, "until": "2014"},
        ),
        "source": "https://www.international.gc.ca/world-monde/international_relations-relations_internationales/g7/index.aspx?lang=eng",
        "notes": (
            "Seven countries; the European Union takes part as a non-enumerated member and is listed as a "
            "non-country member (a group reference, since it has no ISO code). Six countries met from 1975, "
            "CA joined in 1976. RU took part as the G8 until 2014. The G7 has no secretariat; the source is "
            "the Government of Canada's G7 page (Canada held the 2025 presidency)."
        ),
    },
    "legal:g20": {
        "name": "Group of Twenty",
        "aliases": ("G20", "G-20"),
        "kind": "forum",
        "members": (
            {"code": "AR", "since": "1999", "until": None},
            {"code": "AU", "since": "1999", "until": None},
            {"code": "BR", "since": "1999", "until": None},
            {"code": "CA", "since": "1999", "until": None},
            {"code": "CN", "since": "1999", "until": None},
            {"code": "FR", "since": "1999", "until": None},
            {"code": "DE", "since": "1999", "until": None},
            {"code": "IN", "since": "1999", "until": None},
            {"code": "ID", "since": "1999", "until": None},
            {"code": "IT", "since": "1999", "until": None},
            {"code": "JP", "since": "1999", "until": None},
            {"code": "KR", "since": "1999", "until": None},
            {"code": "MX", "since": "1999", "until": None},
            {"code": "RU", "since": "1999", "until": None},
            {"code": "SA", "since": "1999", "until": None},
            {"code": "ZA", "since": "1999", "until": None},
            {"code": "TR", "since": "1999", "until": None},
            {"code": "GB", "since": "1999", "until": None},
            {"code": "US", "since": "1999", "until": None},
            {"code": None, "since": "1999", "until": None, "group": "legal:eu"},
            {"code": None, "since": "2023-09-09", "until": None, "group": "legal:african-union"},
        ),
        "source": "https://g20.org/",
        "notes": (
            "19 countries plus two non-country members: the European Union (since the G20 began in 1999) and "
            "the African Union (admitted at the New Delhi summit on 2023-09-09). Non-country members are "
            "group references because they have no ISO code. Which members and guests attend a given year's "
            "meetings is decided by that year's presidency and is not recorded here."
        ),
    },
    "legal:nato": {
        "name": "North Atlantic Treaty Organization",
        "aliases": ("NATO", "OTAN", "North Atlantic Treaty Organisation", "North Atlantic Alliance"),
        "kind": "alliance",
        "members": (
            {"code": "BE", "since": "1949", "until": None},
            {"code": "CA", "since": "1949", "until": None},
            {"code": "DK", "since": "1949", "until": None},
            {"code": "FR", "since": "1949", "until": None},
            {"code": "IS", "since": "1949", "until": None},
            {"code": "IT", "since": "1949", "until": None},
            {"code": "LU", "since": "1949", "until": None},
            {"code": "NL", "since": "1949", "until": None},
            {"code": "NO", "since": "1949", "until": None},
            {"code": "PT", "since": "1949", "until": None},
            {"code": "GB", "since": "1949", "until": None},
            {"code": "US", "since": "1949", "until": None},
            {"code": "GR", "since": "1952-02-18", "until": None},
            {"code": "TR", "since": "1952-02-18", "until": None},
            {"code": "DE", "since": "1955-05-06", "until": None},
            {"code": "ES", "since": "1982-05-30", "until": None},
            {"code": "CZ", "since": "1999-03-12", "until": None},
            {"code": "HU", "since": "1999-03-12", "until": None},
            {"code": "PL", "since": "1999-03-12", "until": None},
            {"code": "BG", "since": "2004-03-29", "until": None},
            {"code": "EE", "since": "2004-03-29", "until": None},
            {"code": "LV", "since": "2004-03-29", "until": None},
            {"code": "LT", "since": "2004-03-29", "until": None},
            {"code": "RO", "since": "2004-03-29", "until": None},
            {"code": "SK", "since": "2004-03-29", "until": None},
            {"code": "SI", "since": "2004-03-29", "until": None},
            {"code": "AL", "since": "2009-04-01", "until": None},
            {"code": "HR", "since": "2009-04-01", "until": None},
            {"code": "ME", "since": "2017-06-05", "until": None},
            {"code": "MK", "since": "2020-03-27", "until": None},
            {"code": "FI", "since": "2023-04-04", "until": None},
            {"code": "SE", "since": "2024-03-07", "until": None},
        ),
        "source": "https://www.nato.int/cps/en/natohq/topics_52044.htm",
        "notes": (
            "32 member countries. The 12 founders signed the North Atlantic Treaty on 1949-04-04 (year only "
            "here); later dates are the accession dates published by NATO. DE joined as the Federal Republic "
            "of Germany; the reunified Germany has been a member since 1990."
        ),
    },
    "legal:mercosur": {
        "name": "Mercosur",
        "aliases": ("Mercosul", "Southern Common Market", "Mercado Común del Sur", "Mercado Comum do Sul"),
        "kind": "trade-agreement",
        "members": (
            {"code": "AR", "since": "1991", "until": None},
            {"code": "BR", "since": "1991", "until": None},
            {"code": "PY", "since": "1991", "until": None},
            {"code": "UY", "since": "1991", "until": None},
            {"code": "BO", "since": "2024", "until": None},
            {"code": "VE", "since": "2012-07-31", "until": None, "suspended_since": "2017-08-05"},
        ),
        "source": "https://www.mercosur.int/en/about-mercosur/mercosur-countries/",
        "notes": (
            "States Parties: AR, BR, PY, UY (founders, Treaty of Asunción, 1991), BO (full member since "
            "2024, with a transition period to adopt Mercosur rules) and VE (suspended, see its member "
            "note). Associated states are not members."
        ),
    },
    "legal:african-union": {
        "name": "African Union",
        "aliases": ("Union africaine", "União Africana"),
        "kind": "union",
        "members": (
            {"code": "AO", "since": "1975-02-11", "until": None},
            {"code": "BF", "since": "1963-05-25", "until": None},
            {"code": "BI", "since": "1963-05-25", "until": None},
            {"code": "BJ", "since": "1963-05-25", "until": None},
            {"code": "BW", "since": "1966-10-31", "until": None},
            {"code": "CD", "since": "1963-05-25", "until": None},
            {"code": "CF", "since": "1963-05-25", "until": None},
            {"code": "CG", "since": "1963-05-25", "until": None},
            {"code": "CI", "since": "1963-05-25", "until": None},
            {"code": "CM", "since": "1963-05-25", "until": None},
            {"code": "CV", "since": "1975-07-18", "until": None},
            {"code": "DJ", "since": "1977-06-27", "until": None},
            {"code": "DZ", "since": "1963-05-25", "until": None},
            {"code": "EG", "since": "1963-05-25", "until": None},
            {"code": "ER", "since": "1993-05-24", "until": None},
            {"code": "ET", "since": "1963-05-25", "until": None},
            {"code": "GA", "since": "1963-05-25", "until": None},
            {"code": "GH", "since": "1963-05-25", "until": None},
            {"code": "GM", "since": "1965-03-09", "until": None},
            {"code": "GN", "since": "1963-05-25", "until": None},
            {"code": "GQ", "since": "1968-10-12", "until": None},
            {"code": "GW", "since": "1973-11-19", "until": None},
            {"code": "KE", "since": "1963-05-25", "until": None},
            {"code": "KM", "since": "1975-07-18", "until": None},
            {"code": "LR", "since": "1963-05-25", "until": None},
            {"code": "LS", "since": "1966-10-31", "until": None},
            {"code": "LY", "since": "1963-05-25", "until": None},
            {"code": "MA", "since": "2017-01-31", "until": None},
            {"code": "MG", "since": "1963-05-25", "until": None},
            {"code": "ML", "since": "1963-05-25", "until": None},
            {"code": "MR", "since": "1963-05-25", "until": None},
            {"code": "MU", "since": "1968", "until": None},
            {"code": "MW", "since": "1964-07-13", "until": None},
            {"code": "MZ", "since": "1975-07-18", "until": None},
            {"code": "NA", "since": "1990", "until": None},
            {"code": "NE", "since": "1963-05-25", "until": None},
            {"code": "NG", "since": "1963-05-25", "until": None},
            {"code": "RW", "since": "1963-05-25", "until": None},
            {"code": "SC", "since": "1976-06-29", "until": None},
            {"code": "SD", "since": "1963-05-25", "until": None},
            {"code": "SL", "since": "1963-05-25", "until": None},
            {"code": "SN", "since": "1963-05-25", "until": None},
            {"code": "SO", "since": "1963-05-25", "until": None},
            {"code": "SS", "since": "2011-07-27", "until": None},
            {"code": "ST", "since": "1975-07-18", "until": None},
            {"code": "SZ", "since": "1968-09-24", "until": None},
            {"code": "TD", "since": "1963-05-25", "until": None},
            {"code": "TG", "since": "1963-05-25", "until": None},
            {"code": "TN", "since": "1963-05-25", "until": None},
            {"code": "TZ", "since": "1963-05-25", "until": None},
            {"code": "UG", "since": "1963-05-25", "until": None},
            {"code": "ZA", "since": "1994-06-06", "until": None},
            {"code": "ZM", "since": "1964-12-16", "until": None},
            {"code": "ZW", "since": "1980-06-18", "until": None},
            {
                "code": None,
                "since": "1982-02-22",
                "until": None,
                "entity": "Sahrawi Arab Democratic Republic",
            },
        ),
        "source": "https://au.int/en/member_states/countryprofiles2",
        "notes": (
            "55 member states. 'since' is the date of joining the Organisation of African Unity (founded "
            "1963-05-25) or the AU (which succeeded it in 2002), as published by the AU; month-only dates "
            "are given as the year. Suspensions from AU activities after unconstitutional changes of "
            "government change often and are not recorded; see the AU Peace and Security Council for current "
            "status. The abbreviation 'AU' is not an alias because it is Australia's ISO code."
        ),
    },
    "legal:cptpp": {
        "name": "Comprehensive and Progressive Agreement for Trans-Pacific Partnership",
        "aliases": ("CPTPP", "TPP-11", "TPP11"),
        "kind": "trade-agreement",
        "members": (
            {"code": "AU", "since": "2018-12-30", "until": None},
            {"code": "CA", "since": "2018-12-30", "until": None},
            {"code": "JP", "since": "2018-12-30", "until": None},
            {"code": "MX", "since": "2018-12-30", "until": None},
            {"code": "NZ", "since": "2018-12-30", "until": None},
            {"code": "SG", "since": "2018-12-30", "until": None},
            {"code": "VN", "since": "2019-01-14", "until": None},
            {"code": "PE", "since": "2021-09-19", "until": None},
            {"code": "MY", "since": "2022-11-29", "until": None},
            {"code": "CL", "since": "2023-02-21", "until": None},
            {"code": "BN", "since": "2023-07-12", "until": None},
            {"code": "GB", "since": "2024-12-15", "until": None},
        ),
        "source": "https://www.international.gc.ca/trade-commerce/trade-agreements-accords-commerciaux/agr-acc/cptpp-ptpgp/index.aspx?lang=eng",
        "notes": (
            "Twelve parties. 'since' is the date the agreement entered into force for each. For GB it "
            "entered into force on 2024-12-15 with the parties that had ratified by then and on later dates "
            "with the rest (e.g. AU on 2024-12-24). CR concluded accession negotiations in 2026 but is not "
            "yet a party."
        ),
    },
}

# lower-cased name or alias -> group id
ALIASES = {
    "africa": "geo:africa", "african continent": "geo:africa", "antarctica": "geo:antarctica",
    "asia": "geo:asia", "asian continent": "geo:asia", "europe": "geo:europe",
    "european continent": "geo:europe", "eur": "geo:europe", "north america": "geo:north-america",
    "north american continent": "geo:north-america", "south america": "geo:south-america",
    "south american continent": "geo:south-america", "oceania": "geo:oceania",
    "australia and oceania": "geo:oceania", "australia/oceania": "geo:oceania",
    "africa (un m49)": "geo:m49-africa", "africa (m49)": "geo:m49-africa",
    "americas (un m49)": "geo:m49-americas", "americas": "geo:m49-americas",
    "the americas": "geo:m49-americas", "amer": "geo:m49-americas", "asia (un m49)": "geo:m49-asia",
    "asia (m49)": "geo:m49-asia", "europe (un m49)": "geo:m49-europe", "europe (m49)": "geo:m49-europe",
    "oceania (un m49)": "geo:m49-oceania", "oceania (m49)": "geo:m49-oceania",
    "australia and new zealand (un m49)": "geo:m49-australia-new-zealand", "central asia": "geo:central-asia",
    "eastern asia": "geo:eastern-asia", "eastern europe": "geo:eastern-europe",
    "latin america and the caribbean": "geo:latin-america-caribbean", "lac": "geo:latin-america-caribbean",
    "melanesia": "geo:melanesia", "micronesia": "geo:micronesia", "northern africa": "geo:northern-africa",
    "northern america": "geo:northern-america", "northern europe": "geo:northern-europe",
    "polynesia": "geo:polynesia", "south-eastern asia": "geo:south-eastern-asia",
    "southern asia": "geo:southern-asia", "southern europe": "geo:southern-europe",
    "sub-saharan africa": "geo:sub-saharan-africa", "western asia": "geo:western-asia",
    "western europe": "geo:western-europe", "caribbean (un m49)": "geo:m49-caribbean",
    "central america": "geo:central-america", "eastern africa": "geo:eastern-africa",
    "middle africa": "geo:middle-africa", "south america (un m49)": "geo:m49-south-america",
    "southern africa": "geo:southern-africa", "western africa": "geo:western-africa",
    "us & canada": "geo:us-canada", "us and canada": "geo:us-canada", "usa & canada": "geo:us-canada",
    "usa and canada": "geo:us-canada", "us/canada": "geo:us-canada", "u.s. & canada": "geo:us-canada",
    "canada & us": "geo:us-canada", "canada and the us": "geo:us-canada",
    "north america (us & canada)": "geo:us-canada", "us, canada & mexico": "geo:us-canada-mexico",
    "us and canada and mexico": "geo:us-canada-mexico", "world": "geo:world", "worldwide": "geo:world",
    "global": "geo:world", "anywhere": "geo:world", "international": "geo:world", "any location": "geo:world",
    "everywhere": "geo:world", "nordic countries": "geo:nordic", "nordics": "geo:nordic",
    "nordic region": "geo:nordic", "nordic": "geo:nordic", "norden": "geo:nordic",
    "scandinavia": "geo:scandinavia", "scandinavian countries": "geo:scandinavia", "benelux": "geo:benelux",
    "benelux countries": "geo:benelux", "low countries": "geo:benelux", "iberia": "geo:iberia",
    "iberian peninsula": "geo:iberia", "british isles": "geo:british-isles",
    "britain and ireland": "geo:british-isles", "britain & ireland": "geo:british-isles",
    "baltics": "geo:baltics", "baltic states": "geo:baltics", "baltic countries": "geo:baltics",
    "baltic": "geo:baltics", "balkans": "geo:balkans", "the balkans": "geo:balkans",
    "balkan peninsula": "geo:balkans", "balkan countries": "geo:balkans", "dach": "geo:dach",
    "d-a-ch": "geo:dach", "dach region": "geo:dach", "caribbean": "geo:caribbean",
    "caribbean islands": "geo:caribbean", "west indies": "geo:caribbean", "the caribbean": "geo:caribbean",
    "middle east": "geo:middle-east", "mideast": "geo:middle-east", "the middle east": "geo:middle-east",
    "southeast asia": "geo:southeast-asia", "south east asia": "geo:southeast-asia",
    "south-east asia": "geo:southeast-asia", "se asia": "geo:southeast-asia", "emea": "geo:emea",
    "europe, middle east and africa": "geo:emea", "europe, the middle east and africa": "geo:emea",
    "europe middle east africa": "geo:emea", "apac": "geo:apac", "asia-pacific": "geo:apac",
    "asia pacific": "geo:apac", "asia/pacific": "geo:apac", "asiapac": "geo:apac", "asia pac": "geo:apac",
    "latam": "geo:latam", "latin america": "geo:latam", "latam region": "geo:latam",
    "na / namer": "geo:namer", "namer": "geo:namer", "noram": "geo:namer",
    "north america (business region)": "geo:namer", "anz": "geo:anz", "australia and new zealand": "geo:anz",
    "australia & new zealand": "geo:anz", "a/nz": "geo:anz", "mena": "geo:mena",
    "middle east and north africa": "geo:mena", "middle east & north africa": "geo:mena",
    "european union": "legal:eu", "eu": "legal:eu", "euro area": "legal:eurozone",
    "eurozone": "legal:eurozone", "euro zone": "legal:eurozone", "euro-zone": "legal:eurozone",
    "european economic area": "legal:eea", "eea": "legal:eea",
    "european free trade association": "legal:efta", "efta": "legal:efta", "schengen area": "legal:schengen",
    "schengen": "legal:schengen", "schengen zone": "legal:schengen", "schengen countries": "legal:schengen",
    "canzuk": "legal:canzuk", "canzuk countries": "legal:canzuk", "five eyes": "legal:five-eyes",
    "fvey": "legal:five-eyes", "5 eyes": "legal:five-eyes", "five eyes alliance": "legal:five-eyes",
    "cusma / usmca / t-mec": "legal:cusma", "cusma": "legal:cusma", "usmca": "legal:cusma",
    "t-mec": "legal:cusma", "tmec": "legal:cusma", "aceum": "legal:cusma",
    "canada-united states-mexico agreement": "legal:cusma",
    "united states-mexico-canada agreement": "legal:cusma",
    "association of southeast asian nations": "legal:asean", "asean": "legal:asean",
    "gulf cooperation council": "legal:gcc", "gcc": "legal:gcc",
    "cooperation council for the arab states of the gulf": "legal:gcc",
    "commonwealth of nations": "legal:commonwealth", "the commonwealth": "legal:commonwealth",
    "commonwealth": "legal:commonwealth",
    "organisation for economic co-operation and development": "legal:oecd", "oecd": "legal:oecd",
    "organization for economic cooperation and development": "legal:oecd", "group of seven": "legal:g7",
    "g7": "legal:g7", "g-7": "legal:g7", "group of twenty": "legal:g20", "g20": "legal:g20",
    "g-20": "legal:g20", "north atlantic treaty organization": "legal:nato", "nato": "legal:nato",
    "otan": "legal:nato", "north atlantic treaty organisation": "legal:nato",
    "north atlantic alliance": "legal:nato", "mercosur": "legal:mercosur", "mercosul": "legal:mercosur",
    "southern common market": "legal:mercosur", "mercado común del sur": "legal:mercosur",
    "mercado comum do sul": "legal:mercosur", "african union": "legal:african-union",
    "union africaine": "legal:african-union", "união africana": "legal:african-union",
    "comprehensive and progressive agreement for trans-pacific partnership": "legal:cptpp",
    "cptpp": "legal:cptpp", "tpp-11": "legal:cptpp", "tpp11": "legal:cptpp",
}
