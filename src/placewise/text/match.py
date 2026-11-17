"""Filter helpers over parsed locations. Every helper returns a `Decision`: truthy when the location
passes, with a reason a caller can log ("not in CA: Austin, TX (US)")."""

from dataclasses import dataclass

from placewise.constants import countries
from placewise.constants._keys import key
from placewise.constants.location_filter import REMOTE_POLICIES, UNKNOWN_POLICIES
from placewise.constants.work_modes import MODES as WORK_MODES
from placewise.constants.work_modes import REMOTE
from placewise.model._base import Model, set_field

from . import metros as _metros
from . import regions as _regions
from .parse import parse_location

_ADMIN1_TABLES = tuple(countries.SUBREGIONS.items())  # US, CA, IN, GB


@dataclass(frozen=True, slots=True)
class Decision(Model):
    keep: bool
    reason: str

    def __bool__(self):
        return self.keep


# --- Normalising arguments ----------------------------------------------------------------------


def _as_tuple(value):
    return (value,) if isinstance(value, str) else tuple(value)


def _country(text):
    code = countries.lookup(text)
    if code is None:
        raise ValueError(f"unknown country {text!r}")
    return code


def _admin1(text, hint=()):
    """ "CA-ON", "ON" or "Ontario" -> "CA-ON". `hint`: countries that settle a code several
    countries use ("TN" is Tennessee or Tamil Nadu)."""
    if "-" in text and len(text.split("-", 1)[0].strip()) == 2:
        country, code = (p.strip() for p in text.split("-", 1))
        country = _country(country)
        table = dict(_ADMIN1_TABLES).get(country)
        if table is not None:
            found = table.lookup(code)
            if found is None:
                raise ValueError(f"unknown admin1 {text!r}")
            code = found
        return f"{country}-{code.upper()}"
    k = key(text)
    if len(k) == 2:
        found = [(c, k.upper()) for c, table in _ADMIN1_TABLES if k.upper() in table.BY_CODE]
    else:
        found = [(c, table.BY_NAME[k]) for c, table in _ADMIN1_TABLES if k in table.BY_NAME]
    if len(found) > 1 and hint:
        found = [f for f in found if f[0] in hint] or found
    if not found:
        raise ValueError(f"unknown admin1 {text!r}")
    if len(found) > 1:
        options = " or ".join(f"{c}-{code}" for c, code in found)
        raise ValueError(f"ambiguous admin1 {text!r}: write {options}")
    return "-".join(found[0])


def _metro(text):
    metro = _metros.find(text)
    if metro is None:
        raise ValueError(f"unknown metro {text!r}")
    return metro.key


def _describe(part):
    return f"{part.label} ({part.country_iso2})" if part.country_iso2 else part.label


def _in_metro(part, metro_key):
    """(matched, by city name only)."""
    metro = _metros.by_id()[metro_key]
    if part.region == metro_key:
        return True, False
    if part.city and part.admin1_code:
        return _metros.metro_of(part.city, part.country_iso2, part.admin1_code) is metro, False
    if part.city and part.country_iso2 in (None, metro.country) and metro in _metros.metros_naming(part.city):
        return True, True
    return False, False


def _metro_reaches(part, admin1_iso):
    """A part naming a metro that spans this subdivision: "DMV" reaches VA."""
    metro = _metros.by_id().get(part.region) if part.region and not part.admin1_code else None
    if metro is None:
        return False
    country, code = admin1_iso.split("-", 1)
    return metro.country == country and code in metro.admin1


# --- Helpers ------------------------------------------------------------------------------------


def in_country(parsed, country, *, include_alternatives=False):
    """Does a place in `parsed` lie in `country` (a code, name or several)? Alternative readings
    ("London" as London, Ontario) count only with `include_alternatives`."""
    wanted = tuple(dict.fromkeys(_country(c) for c in _as_tuple(country)))
    for part in parsed.parts:
        if part.country_iso2 in wanted:
            return Decision(True, f"in {part.country_iso2}: {part.label}")
    if include_alternatives:
        for part in parsed.parts:
            for alt in part.alternatives:
                if alt.country_iso2 in wanted:
                    reason = f"possibly in {alt.country_iso2}: {alt.label} (confidence {alt.confidence:.2f})"
                    return Decision(True, reason)
    found = [p for p in parsed.parts if p.country_iso2]
    if not found:
        return Decision(False, "no country found")
    return Decision(False, f"not in {'/'.join(wanted)}: " + "; ".join(_describe(p) for p in found))


def in_region(parsed, admin1=(), metro=(), *, include_alternatives=False):
    """Does a place in `parsed` lie in one of these subdivisions ("ON", "CA-ON") or metros ("GTA",
    "SF Bay Area")? A city given without its admin1 matches a metro that lists it by name, and the
    reason says so."""
    admins = [a.upper() for a in _as_tuple(admin1)]
    metro_keys = [_metro(m) for m in _as_tuple(metro)]
    parts = [c for p in parsed.parts for c in (p.candidates() if include_alternatives else (p,))]
    for part in parts:
        for code in admins:
            if (part.iso_3166_2 == code) if "-" in code else (part.admin1_code == code):
                return Decision(True, f"{part.label} is in {code}")
            qualified = code if "-" in code else (f"{part.country_iso2}-{code}" if part.country_iso2 else "")
            if qualified and _metro_reaches(part, qualified):
                return Decision(True, f"{part.region} includes {code}")
        for metro_key in metro_keys:
            matched, by_name = _in_metro(part, metro_key)
            if matched:
                note = " (city name only, unverified)" if by_name else ""
                return Decision(True, f"{part.label} is in {metro_key}{note}")
    targets = ", ".join([*admins, *metro_keys]) or "nothing"
    if not parsed.parts:
        return Decision(False, "no place found")
    return Decision(False, f"not in {targets}: " + "; ".join(_describe(p) for p in parsed.parts))


def is_remote_ok_for(parsed, country):
    """Is `parsed` a remote listing someone in `country` can take? No stated limit counts as yes."""
    code = _country(country)
    if parsed.work_mode != REMOTE:
        return Decision(False, f"not remote ({parsed.work_mode})" if parsed.work_mode else "not remote")
    if not parsed.remote_scope:
        return Decision(True, "remote with no location limit")
    for entry in parsed.remote_scope:
        if entry == code:
            return Decision(True, f"remote within {code}")
        if entry.startswith(f"{code}-"):
            return Decision(True, f"remote limited to {entry}")
        macro = _regions.find(entry)
        if macro is not None and macro.contains(code):
            return Decision(True, f"remote within {macro.name}")
    return Decision(False, f"remote limited to {', '.join(parsed.remote_scope)}")


# --- LocationFilter -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LocationFilter(Model):
    """Which locations a caller wants, built from plain config (TOML / JSON / dict):

    - `countries`: allowed countries; empty allows every country not denied.
    - `admin1` / `metros`: narrow the countries they belong to. With admin1=("CA-ON",) a Canadian
      place must be in Ontario; places in other allowed countries are unaffected. Given without
      `countries`, they also say which countries are allowed.
    - `deny_countries` / `deny_admin1` / `deny_metros`: places never wanted.
    - `remote`: "any" (every remote listing), "scoped" (remote listings with no stated limit or a limit
      that includes an allowed country; the default), "strict" (a stated limit is required) or
      "deny" (remote listings pass only through an office place). Remote listings are judged by country,
      not by the admin1 / metro narrowing.
    - `work_modes`: allowed modes ("remote", "hybrid", "onsite"); empty allows all, and a location
      that names no mode isn't held to them.
    - `unknown`: "keep" or "drop" locations in which no country could be found.
    - `include_alternatives`: let less likely readings pass ("London" as London, Ontario).

    A location with several places passes when any one of them does.
    """

    countries: tuple[str, ...] = ()
    admin1: tuple[str, ...] = ()
    metros: tuple[str, ...] = ()
    deny_countries: tuple[str, ...] = ()
    deny_admin1: tuple[str, ...] = ()
    deny_metros: tuple[str, ...] = ()
    remote: str = "scoped"
    work_modes: tuple[str, ...] = ()
    unknown: str = "keep"
    include_alternatives: bool = False

    def __post_init__(self):
        allowed = tuple(dict.fromkeys(_country(c) for c in _as_tuple(self.countries)))
        set_field(self, "countries", allowed)
        set_field(
            self, "deny_countries", tuple(dict.fromkeys(_country(c) for c in _as_tuple(self.deny_countries)))
        )
        for name in ("admin1", "deny_admin1"):
            set_field(
                self, name, tuple(dict.fromkeys(_admin1(a, allowed) for a in _as_tuple(getattr(self, name))))
            )
        for name in ("metros", "deny_metros"):
            set_field(self, name, tuple(dict.fromkeys(_metro(m) for m in _as_tuple(getattr(self, name)))))
        set_field(self, "work_modes", _as_tuple(self.work_modes))
        if self.remote not in REMOTE_POLICIES:
            raise ValueError(f"remote must be one of {', '.join(REMOTE_POLICIES)}, not {self.remote!r}")
        if self.unknown not in UNKNOWN_POLICIES:
            raise ValueError(f"unknown must be one of {', '.join(UNKNOWN_POLICIES)}, not {self.unknown!r}")
        for mode in self.work_modes:
            if mode not in WORK_MODES:
                raise ValueError(f"unknown work mode {mode!r}")

    def _narrowing(self):
        """country -> the admin1 codes and metros allowed in it."""
        out = {}
        for code in self.admin1:
            out.setdefault(code.split("-", 1)[0], []).append(code)
        for metro_key in self.metros:
            out.setdefault(_metros.by_id()[metro_key].country, []).append(metro_key)
        return out

    def _allowed_countries(self):
        return set(self.countries) | set(self._narrowing())

    def _judge(self, part):
        """("deny" | "allow" | "reject", reason) for one reading of a place."""
        country = part.country_iso2
        if country in self.deny_countries or (part.iso_3166_2 and part.iso_3166_2 in self.deny_admin1):
            return "deny", _describe(part)
        if any(_in_metro(part, m)[0] for m in self.deny_metros):
            return "deny", _describe(part)
        narrowing = self._narrowing()
        entries = narrowing.get(country)
        if entries:
            for entry in entries:
                if entry == part.iso_3166_2 or (entry in self.metros and _in_metro(part, entry)[0]):
                    return "allow", f"{part.label} is in an allowed region ({entry})"
            return "reject", f"{part.label} ({country}; allowed there: {', '.join(entries)})"
        if not self.countries and not narrowing:
            return "allow", f"{_describe(part)} is allowed"
        if country in self.countries:
            return "allow", f"{part.label} is in an allowed country ({country})"
        return "reject", _describe(part)

    def _judge_remote(self, parsed):
        if self.remote == "deny":
            return Decision(False, "remote is not allowed")
        if self.remote == "any":
            return Decision(True, "remote (any location allowed)")
        scope = parsed.remote_scope
        if not scope:
            if self.remote == "strict":
                return Decision(False, "remote with no stated location")
            return Decision(True, "remote with no location limit")
        allowed = self._allowed_countries()
        for entry in scope:
            macro = _regions.find(entry) if "-" not in entry and len(entry) != 2 else None
            if macro is not None:
                if not allowed or any(macro.contains(c) for c in allowed - set(self.deny_countries)):
                    return Decision(True, f"remote within {macro.name}")
                continue
            country = entry.split("-", 1)[0]
            if country in self.deny_countries or entry in self.deny_admin1:
                continue
            if not allowed or country in allowed:
                return Decision(True, f"remote within {entry}")
        return Decision(False, f"remote limited to {', '.join(scope)}")

    def decide(self, location, gazetteer=None):
        """Keep or drop a location (a ParsedLocation, or text to parse), with the reason."""
        parsed = parse_location(location, gazetteer) if isinstance(location, str) else location
        if self.work_modes and parsed.work_modes and not set(parsed.work_modes) & set(self.work_modes):
            return Decision(False, f"work mode {parsed.work_mode} is not allowed")
        remote = parsed.work_mode == REMOTE
        denied, rejected = [], []
        for part in parsed.parts:
            if part.remote and remote:
                continue  # a remote listing's limit, judged below
            readings = part.candidates() if self.include_alternatives else (part,)
            for reading in readings:
                if reading.country_iso2 is None:
                    continue
                verdict, reason = self._judge(reading)
                if verdict == "allow":
                    return Decision(True, reason)
                (denied if verdict == "deny" else rejected).append(reason)
        if remote:
            decision = self._judge_remote(parsed)
            if decision or not (denied or rejected):
                return decision
        if rejected:
            return Decision(False, "not in an allowed location: " + "; ".join(dict.fromkeys(rejected)))
        if denied:
            return Decision(False, "denied: " + "; ".join(dict.fromkeys(denied)))
        if self.unknown == "keep":
            return Decision(True, "no country found (kept: unknown locations are kept)")
        return Decision(False, "no country found (dropped: unknown locations are dropped)")
