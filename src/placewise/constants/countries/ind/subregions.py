"""Indian states and union territories (ISO 3166-2:IN).

Sources:
- Codes: ISO 3166-2:IN as of the ISO 3166 Maintenance Agency change of 2023-11-23, which replaced
  IN-OR with IN-OD (Odisha), IN-CT with IN-CG (Chhattisgarh), IN-TG with IN-TS (Telangana) and
  IN-UT with IN-UK (Uttarakhand); earlier changes added Ladakh (IN-LA, 2019) and merged Dadra and
  Nagar Haveli (IN-DN) with Daman and Diu (IN-DD) into IN-DH (2020).
  https://www.iso.org/obp/ui/#iso:code:3166:IN
- Names: Government of India, National Portal of India, "States and Union Territories",
  https://knowindia.india.gov.in/states-uts/ (English names, without diacritics).

`code` is the part after "IN-". The replaced codes and old names (Orissa, Pondicherry, Uttaranchal)
are aliases, because location strings still use them; so are common short forms ("J&K"). The package is
`ind` (ISO alpha-3, lower case).
"""

from dataclasses import dataclass

from ..._keys import key


@dataclass(frozen=True, slots=True)
class State:
    name: str
    code: str  # ISO 3166-2:IN without the "IN-" prefix
    kind: str  # "state" or "union_territory"
    aliases: tuple[str, ...] = ()

    @property
    def iso(self):
        return f"IN-{self.code}"


SUBREGIONS = (
    State("Andhra Pradesh", "AP", "state"),
    State("Arunachal Pradesh", "AR", "state"),
    State("Assam", "AS", "state"),
    State("Bihar", "BR", "state"),
    State("Chhattisgarh", "CG", "state", ("CT", "Chattisgarh")),
    State("Goa", "GA", "state"),
    State("Gujarat", "GJ", "state"),
    State("Haryana", "HR", "state"),
    State("Himachal Pradesh", "HP", "state"),
    State("Jharkhand", "JH", "state"),
    State("Karnataka", "KA", "state"),
    State("Kerala", "KL", "state"),
    State("Madhya Pradesh", "MP", "state"),
    State("Maharashtra", "MH", "state"),
    State("Manipur", "MN", "state"),
    State("Meghalaya", "ML", "state"),
    State("Mizoram", "MZ", "state"),
    State("Nagaland", "NL", "state"),
    State("Odisha", "OD", "state", ("OR", "Orissa")),
    State("Punjab", "PB", "state"),
    State("Rajasthan", "RJ", "state"),
    State("Sikkim", "SK", "state"),
    State("Tamil Nadu", "TN", "state"),
    State("Telangana", "TS", "state", ("TG",)),
    State("Tripura", "TR", "state"),
    State("Uttar Pradesh", "UP", "state"),
    State("Uttarakhand", "UK", "state", ("UT", "Uttaranchal")),
    State("West Bengal", "WB", "state"),
    State("Andaman and Nicobar Islands", "AN", "union_territory", ("Andaman and Nicobar",)),
    State("Chandigarh", "CH", "union_territory"),
    State(
        "Dadra and Nagar Haveli and Daman and Diu",
        "DH",
        "union_territory",
        ("DN", "DD", "Dadra and Nagar Haveli", "Daman and Diu"),
    ),
    State("Delhi", "DL", "union_territory", ("NCT of Delhi", "National Capital Territory of Delhi")),
    State("Jammu and Kashmir", "JK", "union_territory", ("J&K",)),
    State("Ladakh", "LA", "union_territory"),
    State("Lakshadweep", "LD", "union_territory"),
    State("Puducherry", "PY", "union_territory", ("Pondicherry",)),
)

STATES = SUBREGIONS
BY_CODE = {s.code: s for s in SUBREGIONS}
# names, old names and replaced codes, normalised (see _keys.key), to the current code
BY_NAME = {key(n): s.code for s in SUBREGIONS for n in (s.name, *s.aliases)}


def lookup(text):
    """Current ISO code (without "IN-") for a code, former code, name or alias, or None."""
    k = key(text)
    if k.upper() in BY_CODE:
        return k.upper()
    return BY_NAME.get(k)
