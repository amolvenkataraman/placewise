"""US states, the District of Columbia and the five inhabited territories (ISO 3166-2:US).

Sources:
- USPS two-letter codes: USPS Publication 28, Appendix B ("State Abbreviations"),
  https://pe.usps.com/text/pub28/28apb.htm
- FIPS state codes (ANSI INCITS 38): US Census Bureau, "State FIPS codes",
  https://www.census.gov/library/reference/code-lists/ansi.html
- Traditional abbreviations ("Calif.", "N. Mex."): US Government Publishing Office Style Manual
  (2016), "Abbreviations and Letter Symbols", table of state abbreviations; the shorter
  newspaper forms some texts use ("Kan.", "Neb.", "Ore.") are kept as extra aliases.

The freely associated states (FM, MH, PW), US Minor Outlying Islands (no USPS code) and the
military "states" (AA, AE, AP) are left out: they aren't places a person or a business is located in.
"""

from dataclasses import dataclass

from ..._keys import key


@dataclass(frozen=True, slots=True)
class State:
    name: str
    code: str  # USPS code, also the ISO 3166-2:US suffix
    fips: str  # two digits, zero padded
    kind: str  # "state", "district" or "territory"
    aliases: tuple[str, ...] = ()

    @property
    def usps(self):
        return self.code

    @property
    def iso(self):
        """ISO 3166-2 code: "US-CA". The territories have their own ISO 3166-1 codes too (PR ...)."""
        return f"US-{self.code}"


SUBREGIONS = (
    State("Alabama", "AL", "01", "state", ("Ala.",)),
    State("Alaska", "AK", "02", "state"),
    State("Arizona", "AZ", "04", "state", ("Ariz.",)),
    State("Arkansas", "AR", "05", "state", ("Ark.",)),
    State("California", "CA", "06", "state", ("Calif.", "Cal.")),
    State("Colorado", "CO", "08", "state", ("Colo.",)),
    State("Connecticut", "CT", "09", "state", ("Conn.",)),
    State("Delaware", "DE", "10", "state", ("Del.",)),
    State("District of Columbia", "DC", "11", "district", ("D.C.",)),
    State("Florida", "FL", "12", "state", ("Fla.",)),
    State("Georgia", "GA", "13", "state", ("Ga.",)),
    State("Hawaii", "HI", "15", "state", ("Hawai'i",)),
    State("Idaho", "ID", "16", "state"),
    State("Illinois", "IL", "17", "state", ("Ill.",)),
    State("Indiana", "IN", "18", "state", ("Ind.",)),
    State("Iowa", "IA", "19", "state"),
    State("Kansas", "KS", "20", "state", ("Kans.", "Kan.")),
    State("Kentucky", "KY", "21", "state", ("Ky.",)),
    State("Louisiana", "LA", "22", "state", ("La.",)),
    State("Maine", "ME", "23", "state"),
    State("Maryland", "MD", "24", "state", ("Md.",)),
    State("Massachusetts", "MA", "25", "state", ("Mass.",)),
    State("Michigan", "MI", "26", "state", ("Mich.",)),
    State("Minnesota", "MN", "27", "state", ("Minn.",)),
    State("Mississippi", "MS", "28", "state", ("Miss.",)),
    State("Missouri", "MO", "29", "state", ("Mo.",)),
    State("Montana", "MT", "30", "state", ("Mont.",)),
    State("Nebraska", "NE", "31", "state", ("Nebr.", "Neb.")),
    State("Nevada", "NV", "32", "state", ("Nev.",)),
    State("New Hampshire", "NH", "33", "state", ("N.H.",)),
    State("New Jersey", "NJ", "34", "state", ("N.J.",)),
    State("New Mexico", "NM", "35", "state", ("N. Mex.", "N.M.")),
    State("New York", "NY", "36", "state", ("N.Y.",)),
    State("North Carolina", "NC", "37", "state", ("N.C.",)),
    State("North Dakota", "ND", "38", "state", ("N. Dak.", "N.D.")),
    State("Ohio", "OH", "39", "state"),
    State("Oklahoma", "OK", "40", "state", ("Okla.",)),
    State("Oregon", "OR", "41", "state", ("Oreg.", "Ore.")),
    State("Pennsylvania", "PA", "42", "state", ("Pa.", "Penn.", "Penna.")),
    State("Rhode Island", "RI", "44", "state", ("R.I.",)),
    State("South Carolina", "SC", "45", "state", ("S.C.",)),
    State("South Dakota", "SD", "46", "state", ("S. Dak.", "S.D.")),
    State("Tennessee", "TN", "47", "state", ("Tenn.",)),
    State("Texas", "TX", "48", "state", ("Tex.",)),
    State("Utah", "UT", "49", "state"),
    State("Vermont", "VT", "50", "state", ("Vt.",)),
    State("Virginia", "VA", "51", "state", ("Va.",)),
    State("Washington", "WA", "53", "state", ("Wash.", "Washington State")),
    State("West Virginia", "WV", "54", "state", ("W. Va.",)),
    State("Wisconsin", "WI", "55", "state", ("Wis.", "Wisc.")),
    State("Wyoming", "WY", "56", "state", ("Wyo.",)),
    State("American Samoa", "AS", "60", "territory"),
    State("Guam", "GU", "66", "territory"),
    State("Northern Mariana Islands", "MP", "69", "territory"),
    State("Puerto Rico", "PR", "72", "territory", ("P.R.",)),
    State("U.S. Virgin Islands", "VI", "78", "territory", ("Virgin Islands", "V.I.", "USVI")),
)

STATES = SUBREGIONS
BY_CODE = {s.code: s for s in SUBREGIONS}
BY_FIPS = {s.fips: s for s in SUBREGIONS}
# every name and alias, normalised (see _keys.key), to its USPS code; codes themselves are not here
BY_NAME = {key(n): s.code for s in SUBREGIONS for n in (s.name, *s.aliases)}


def lookup(text):
    """USPS code for a code, name or abbreviation ("NY", "New York", "N.Y."), or None."""
    k = key(text)
    if k.upper() in BY_CODE:
        return k.upper()
    return BY_NAME.get(k)
