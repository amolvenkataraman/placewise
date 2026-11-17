"""The United Kingdom's four countries (ISO 3166-2:GB "country" and "province" subdivisions).

Source: ISO 3166-2:GB, https://www.iso.org/obp/ui/#iso:code:3166:GB (ENG England, SCT Scotland,
WLS Wales, NIR Northern Ireland). Postings name them as if they were countries ("London,
England"); placewise reads them as the UK's admin1, as GeoNames does.
Counties and council areas are left to the data packs.
"""

from dataclasses import dataclass

from ..._keys import key


@dataclass(frozen=True, slots=True)
class Nation:
    name: str
    code: str  # ISO 3166-2:GB suffix
    aliases: tuple[str, ...] = ()

    @property
    def iso(self):
        return f"GB-{self.code}"


SUBREGIONS = (
    Nation("England", "ENG"),
    Nation("Scotland", "SCT"),
    Nation("Wales", "WLS", ("Cymru",)),
    Nation("Northern Ireland", "NIR", ("N. Ireland", "NI")),
)

NATIONS = SUBREGIONS
BY_CODE = {n.code: n for n in SUBREGIONS}
BY_NAME = {key(a): n.code for n in SUBREGIONS for a in (n.name, *n.aliases)}


def lookup(text):
    """ISO suffix for a code or name ("ENG", "England"), or None."""
    k = key(text)
    if k.upper() in BY_CODE:
        return k.upper()
    return BY_NAME.get(k)
