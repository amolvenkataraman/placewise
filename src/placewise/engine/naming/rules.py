"""Pure naming rules on plain values: no packs, no arrays (docs/naming.md)."""

import unicodedata

from placewise.constants import naming as const

MUNICIPAL, RURAL, UNORGANIZED = "municipal", "rural", "unorganized"


def title_cities(title, known):
    """The principal cities a CBSA or CSA title names, in order ("Las Vegas-Henderson-North Las
    Vegas, NV"). Names are joined on "-"; hyphenated names ("Winston-Salem") are kept whole when
    known(name) says such a place exists, and "--" always separates. Unknown names are skipped."""
    names = title.rpartition(",")[0] if "," in title else title
    out = []
    for group in names.split("--"):
        tokens = [t.strip() for t in group.split("-")]
        i = 0
        while i < len(tokens):
            for j in range(len(tokens), i, -1):
                name = "-".join(tokens[i:j])
                if known(name):
                    out.append(name)
                    i = j
                    break
            else:
                i += 1
    return out


def title_states(title):
    """The USPS state codes a CBSA or CSA title ends with ("NY-NJ" -> ["NY", "NJ"])."""
    return [s.strip() for s in title.rpartition(",")[2].split("-") if s.strip()] if "," in title else []


def cma_cities(name):
    """The cities a census metropolitan area's name lists ("Kitchener - Cambridge - Waterloo")."""
    return [part.strip() for part in name.split(" - ") if part.strip()]


def rolls_up(population, head_population):
    """Whether a locality's city is its metro's head city rather than itself: it has fewer than
    CITY_KEEP_POPULATION people and the head has CITY_ROLL_UP_RATIO times as many. Unknown
    populations never roll up."""
    if population is None or head_population is None or population < 0 or head_population < 0:
        return False
    return (
        population < const.CITY_KEEP_POPULATION and head_population >= const.CITY_ROLL_UP_RATIO * population
    )


def csd_kind(csdtype):
    """MUNICIPAL, RURAL or UNORGANIZED for a StatCan census subdivision type code."""
    if csdtype in const.CSD_UNORGANIZED:
        return UNORGANIZED
    if csdtype in const.CSD_RURAL:
        return RURAL
    return MUNICIPAL


def office_area_name(name):
    """A post office's name without its type ("Whitefield S.O" -> "Whitefield"): the words before
    the first type word, which may be followed by the town it reports to ("Gandhi Bazar SO
    Amritsar") or a district in brackets ("Old Town S.O (Khorda)"). Nothing left: the name."""
    words = name.split()
    types = {t.upper() for t in const.OFFICE_SUFFIXES}
    cut = next((i for i, w in enumerate(words) if i and w.upper() in types), len(words))
    area = " ".join(words[:cut]).strip()
    return area or name.strip()


def fold(name):
    """A name for comparison: case and accents ignored."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def same_name(a, b):
    return bool(a) and bool(b) and fold(a) == fold(b)
