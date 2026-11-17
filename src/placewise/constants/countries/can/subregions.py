"""Canadian provinces and territories (ISO 3166-2:CA).

Sources:
- Two-letter codes and SGC codes: Statistics Canada, Standard Geographical Classification (SGC)
  2021, "Province and territory codes and abbreviations",
  https://www.statcan.gc.ca/en/subjects/standard/sgc/2021/introduction (the two-letter codes are
  Canada Post's and match ISO 3166-2:CA).
- Traditional English abbreviations ("Ont.", "Que.", "B.C."): the same Statistics Canada table.
- French names: the official French names on the same table.

placewise is English-only for output: `name` is the English name, and the French names and the
abbreviations are aliases for reading input only.
"""

from dataclasses import dataclass

from ..._keys import key


@dataclass(frozen=True, slots=True)
class Province:
    name: str
    code: str  # Canada Post / ISO 3166-2:CA
    sgc: str  # Statistics Canada SGC province code
    kind: str  # "province" or "territory"
    aliases: tuple[str, ...] = ()  # English abbreviations, then the French name

    @property
    def iso(self):
        return f"CA-{self.code}"


SUBREGIONS = (
    Province(
        "Newfoundland and Labrador",
        "NL",
        "10",
        "province",
        ("N.L.", "Nfld.", "Nfld. Lab.", "Newfoundland", "Terre-Neuve-et-Labrador"),
    ),
    Province("Prince Edward Island", "PE", "11", "province", ("P.E.I.", "PEI", "Île-du-Prince-Édouard")),
    Province("Nova Scotia", "NS", "12", "province", ("N.S.", "Nouvelle-Écosse")),
    Province("New Brunswick", "NB", "13", "province", ("N.B.", "Nouveau-Brunswick")),
    Province("Quebec", "QC", "24", "province", ("Que.", "Qué.", "Québec")),
    Province("Ontario", "ON", "35", "province", ("Ont.",)),
    Province("Manitoba", "MB", "46", "province", ("Man.",)),
    Province("Saskatchewan", "SK", "47", "province", ("Sask.",)),
    Province("Alberta", "AB", "48", "province", ("Alta.",)),
    Province("British Columbia", "BC", "59", "province", ("B.C.", "Colombie-Britannique")),
    Province("Yukon", "YT", "60", "territory", ("Y.T.", "Yukon Territory")),
    Province(
        "Northwest Territories", "NT", "61", "territory", ("N.W.T.", "NWT", "Territoires du Nord-Ouest")
    ),
    Province("Nunavut", "NU", "62", "territory", ("Nvt.",)),
)

PROVINCES = SUBREGIONS
BY_CODE = {p.code: p for p in SUBREGIONS}
BY_SGC = {p.sgc: p for p in SUBREGIONS}
BY_NAME = {key(n): p.code for p in SUBREGIONS for n in (p.name, *p.aliases)}


def lookup(text):
    """Two-letter code for a code, name or alias ("ON", "Ontario", "Ont."), or None."""
    k = key(text)
    if k.upper() in BY_CODE:
        return k.upper()
    return BY_NAME.get(k)
