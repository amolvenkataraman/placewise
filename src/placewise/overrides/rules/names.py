"""Forward search by override: the entity ids a name means under alias, rename, region and add
rules."""

from placewise.constants import overrides as const
from placewise.geo.distances import haversine
from placewise.model import Add, Alias, Hide, RegionRule, Rename


def resolve_name(entries, text, country=None, near=None):
    """Entity ids `text` means, highest precedence first; see OverrideEngine.resolve_name."""
    key = _norm(text)
    hidden = {
        e.rule.id
        for e in entries
        if isinstance(e.rule, Hide) or (isinstance(e.rule, RegionRule) and e.rule.remove)
    }
    found = []
    for entry in reversed(entries):
        rule = entry.rule
        if isinstance(rule, Alias):
            if not _alias_applies(rule, country, near):
                continue
            names, target = (rule.text,), rule.means
        elif isinstance(rule, Rename):
            names, target = (rule.name, *rule.aliases), rule.id
        elif isinstance(rule, RegionRule) and not rule.remove:
            names, target = (*((rule.label,) if rule.label else ()), *rule.aliases), rule.id
        elif isinstance(rule, Add) and rule.id:
            names, target = (rule.name,), rule.id
        else:
            continue
        if target not in hidden and target not in found and any(_norm(n) == key for n in names):
            found.append(target)
    return found


def _norm(text):
    return " ".join(str(text).casefold().split())


def _alias_applies(rule, country, near):
    if rule.country and country and rule.country.upper() != country.upper():
        return False
    if rule.near is not None and near is not None:
        lat, lon = (near.lat, near.lon) if hasattr(near, "lat") else near
        return float(haversine(rule.near.lat, rule.near.lon, lat, lon)) <= const.ALIAS_NEAR_KM
    return True
