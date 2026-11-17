"""Pure naming rules on plain values: no packs, no arrays (docs/naming.md)."""

import unicodedata

from placewise.constants import naming as const

MUNICIPAL, RURAL, UNORGANIZED = "municipal", "rural", "unorganized"


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


def extends(name, base):
    """Whether `name` is `base` with words added ("East Los Angeles" extends "Los Angeles"; "Los
    Angeles" doesn't extend itself, "Losa" doesn't extend "Los")."""
    words, inner = fold(name).split(), fold(base).split()
    n = len(inner)
    return 0 < n < len(words) and any(words[i : i + n] == inner for i in range(len(words) - n + 1))


def same_name(a, b):
    return bool(a) and bool(b) and fold(a) == fold(b)
