"""Data licences the build accepts (SPDX identifiers, or LicenseRef- for ones SPDX lacks)."""

KNOWN = frozenset(
    {
        "LicenseRef-public-domain",  # US federal works, Natural Earth
        "CC0-1.0",
        "PDDL-1.0",
        "CC-BY-4.0",
        "CC-BY-3.0-IGO",
        "ODC-By-1.0",
        "OGL-UK-3.0",
        "OGL-Canada-2.0",
        "LicenseRef-StatCan-Open-Licence",
        "etalab-2.0",
        "DL-DE-BY-2.0",
        "NLOD-2.0",
        "OGDL-Taiwan-1.0",
        "LicenseRef-GODL-India",
        "CDLA-Permissive-2.0",
        "Unicode-3.0",  # Unicode License v3 (Unicode CLDR): permissive, keep the copyright notice
        "ODbL-1.0",
        "CC-BY-SA-4.0",
    }
)
# allowed only in the separate share-alike pack
SHARE_ALIKE = frozenset({"ODbL-1.0", "CC-BY-SA-4.0"})
# ODbL makes whoever distributes a derived database offer it (and its recipe) somewhere
NEEDS_DERIVED_DATABASE = frozenset({"ODbL-1.0"})
# sources whose terms forbid redistribution or commercial use: never shipped, never used to clean others
DENIED_SOURCES = frozenset(
    {
        "gadm",
        "hydrorivers",  # HydroSHEDS v1 licence: no stand-alone redistribution (constants.water)
        "marineregions-iho",  # IHO Sea Areas: CC BY-NC-SA 4.0 (constants.water)
        "wdpa",
        "wikivoyage",
    }
)
