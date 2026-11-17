"""The overrides engine: rules from the repo, the calling app and the user's own file, applied to answers.

Layers stack DATA < REPO < APP < LOCAL. `apply` runs the rules from the lowest layer to the highest
(file order within a layer), so a higher layer, or a later rule in the same layer, has the last
word. Tune rules are merged first (knob by knob, same precedence) and applied once at the end, so a
lower layer can't throw away entries that a higher layer's wider radius would keep.

Every field a rule changes is cited in `Result.sources[field]` as "override:<origin>", where origin
is "<layer>:<file>#<rule number>" ("repo:aliases.toml#1", "local:overrides.toml#3", "app#2"). Local
files are cited by file name only, so answers never carry the user's directory layout.
"""

import dataclasses
from pathlib import Path

from placewise import _toml
from placewise.constants import overrides as const
from placewise.geo.distances import haversine
from placewise.model import (
    Add,
    Alias,
    AreaSelector,
    CityRule,
    Hide,
    Label,
    Layer,
    Nearby,
    OverrideSet,
    Place,
    PlaceKind,
    RegionRule,
    Rename,
    Tune,
)
from placewise.model.overrides import RULE_TYPES
from placewise.model.places import Relation

REPO_DIR = Path(__file__).parent / "repo"

PLACE_FIELDS = ("country", "admin1", "admin2", "city", "locality", "sublocality", "borough")
LIST_FIELDS = ("regions", "within")
NEARBY_FIELDS = ("airport", "water")
TUNE_KNOBS = ("tier", "near_km", "fame", "boost")

# kind of the place a label rule creates when the answer has nothing in that field yet
_FIELD_KIND = {
    "city": PlaceKind.LOCALITY,
    "locality": PlaceKind.LOCALITY,
    "sublocality": PlaceKind.SUBLOCALITY,
    "borough": PlaceKind.BOROUGH,
    "admin1": PlaceKind.ADMIN1,
    "admin2": PlaceKind.ADMIN2,
}
_TYPE_NAMES = {rule_type: name for name, rule_type in RULE_TYPES.items()}


@dataclasses.dataclass(frozen=True, slots=True)
class _Entry:
    rule: object
    layer: Layer
    base_dir: Path | None  # relative GeoJSON paths in the rule resolve against this


class _State:
    """The answer being rewritten: mutable copies of the fields rules touch."""

    __slots__ = ("fields", "label_set", "names_changed", "sources")

    def __init__(self, result):
        self.fields = {name: getattr(result, name) for name in ("label", *PLACE_FIELDS, *NEARBY_FIELDS)}
        for name in (*LIST_FIELDS, "near"):
            self.fields[name] = list(getattr(result, name))
        self.sources = dict(result.sources)
        self.label_set = False  # a label rule set the label text itself
        self.names_changed = None  # origin of the last rule that changed a name

    def mark(self, field, origin):
        self.sources[field] = _tag(origin)

    @property
    def cc(self):
        country = self.fields["country"]
        return country.codes.get("iso2") if country else None

    @property
    def place_ids(self):
        ids = {p.id for name in PLACE_FIELDS if (p := self.fields[name]) is not None}
        ids.update(p.id for name in LIST_FIELDS for p in self.fields[name])
        return ids

    def map_places(self, fn):
        """Replace places everywhere they appear. fn(place) -> (new place, origin) or None.
        Returns the origins used, so callers can tell whether anything changed."""
        used = []

        def swap(place, field):
            out = fn(place)
            if out is None or out[0] == place:
                return place
            self.mark(field, out[1])
            used.append(out[1])
            return out[0]

        for name in PLACE_FIELDS:
            if self.fields[name] is not None:
                self.fields[name] = swap(self.fields[name], name)
        for name in LIST_FIELDS:
            self.fields[name] = [swap(p, name) for p in self.fields[name]]
        self.fields["near"] = [_with_place(n, swap(n.place, "near")) for n in self.fields["near"]]
        for name in NEARBY_FIELDS:
            if (n := self.fields[name]) is not None:
                self.fields[name] = _with_place(n, swap(n.place, name))
        return used


class OverrideEngine:
    """Rules from every layer, in the order they apply. Build one with `load_overrides`."""

    __slots__ = ("_entries",)

    def __init__(self, sets=()):
        """`sets`: OverrideSets, or (OverrideSet, base_dir) pairs for rules read from a file."""
        entries = []
        for item in sets:
            override_set, base_dir = item if isinstance(item, tuple) else (item, None)
            entries.extend(_Entry(rule, override_set.layer, base_dir) for rule in override_set.rules)
        entries.sort(key=lambda e: e.layer.precedence)  # stable: file and rule order survive
        self._entries = tuple(entries)

    @classmethod
    def from_documents(cls, documents):
        """From (layer, document, origin) or (layer, document, origin, base_dir) tuples."""
        sets = []
        for layer, doc, origin, *rest in documents:
            sets.append((OverrideSet.from_dict(layer, doc, origin), rest[0] if rest else None))
        return cls(sets)

    @property
    def rules(self):
        return tuple(e.rule for e in self._entries)

    def __len__(self):
        return len(self._entries)

    def __repr__(self):
        counts = {}
        for e in self._entries:
            counts[e.layer.value] = counts.get(e.layer.value, 0) + 1
        return f"OverrideEngine({counts})"

    # --- reverse lookups ------------------------------------------------------------------------

    def apply(self, result, lat, lon, relabel=None):
        """A new Result with every rule applied. `relabel(result) -> str`, if given, recomposes the
        label after a rule renamed something it shows (unless a label rule set the label text)."""
        state = _State(result)
        for entry in self._entries:
            handler = _HANDLERS.get(type(entry.rule))
            if handler is not None:
                handler(state, entry, lat, lon)
        self._apply_tuning(state)

        fields = dict(state.fields)
        for name in (*LIST_FIELDS, "near"):
            fields[name] = tuple(fields[name])
        out = dataclasses.replace(result, **fields, sources=state.sources)
        if relabel is not None and state.names_changed is not None and not state.label_set:
            label = relabel(out)
            if label != out.label:
                out = dataclasses.replace(
                    out, label=label, sources={**out.sources, "label": _tag(state.names_changed)}
                )
        return out

    def tuning(self, place=None, *, id=None, kind=None):
        """Merged Tune knobs ({"tier", "near_km", "fame", "boost"}, only those set) for a place, or for
        rules targeting exactly an id or a kind. Higher layers and later rules win knob by knob."""
        return {knob: value for knob, (value, _) in self._knobs(place, id, kind).items()}

    def _knobs(self, place, id_, kind):
        """{knob: (value, origin)} from the Tune rules that apply."""
        kind = PlaceKind(kind) if kind is not None else None

        def hit(rule):
            if place is not None:
                return rule.id == place.id if rule.id is not None else rule.kind == place.kind
            return (id_ is not None and rule.id == id_) or (kind is not None and rule.kind == kind)

        out = {}
        for entry in self._entries:
            if isinstance(entry.rule, Tune) and hit(entry.rule):
                for knob in TUNE_KNOBS:
                    if (value := getattr(entry.rule, knob)) is not None:
                        out[knob] = (value, entry.rule.origin)
        return out

    def _apply_tuning(self, state):
        if not any(isinstance(e.rule, Tune) for e in self._entries):
            return

        def retier(place):
            tier = self._knobs(place, None, None).get("tier")
            if tier is None or place.tier == tier[0]:
                return None
            return dataclasses.replace(place, tier=tier[0]), tier[1]

        state.map_places(retier)

        def too_far(nearby):
            limit = self._knobs(nearby.place, None, None).get("near_km")
            if nearby.relation is Relation.NEAR and limit is not None and nearby.distance_km > limit[0]:
                return limit[1]
            return None

        kept = []
        for nearby in state.fields["near"]:
            if (origin := too_far(nearby)) is not None:
                state.mark("near", origin)
            else:
                kept.append(nearby)
        state.fields["near"] = kept
        for name in NEARBY_FIELDS:
            if (nearby := state.fields[name]) is not None and (origin := too_far(nearby)) is not None:
                state.fields[name] = None
                state.mark(name, origin)

    # --- forward search -------------------------------------------------------------------------

    def resolve_name(self, text, country=None, near=None):
        """Entity ids a name means by override, highest precedence first: alias rules, plus the
        names and aliases given by rename, region and add rules. `country` (ISO alpha-2) and
        `near` ((lat, lon)) skip aliases restricted to somewhere else. Ids hidden or removed by a
        rule are left out."""
        key = _norm(text)
        hidden = {
            e.rule.id
            for e in self._entries
            if isinstance(e.rule, Hide) or (isinstance(e.rule, RegionRule) and e.rule.remove)
        }
        found = []
        for entry in reversed(self._entries):
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

    def explain(self):
        """Every rule, in the order it applies: [{"layer", "type", "origin", "rule"}]."""
        rows = []
        for entry in self._entries:
            rule = entry.rule.to_dict()
            rule.pop("origin", None)
            rows.append(
                {
                    "layer": entry.layer.value,
                    "type": _TYPE_NAMES[type(entry.rule)],
                    "origin": entry.rule.origin,
                    "rule": rule,
                }
            )
        return rows


# --- one handler per rule type ------------------------------------------------------------------


def _rename(state, entry, lat, lon):
    rule = entry.rule

    def renamed(place):
        if place.id != rule.id:
            return None
        old = (place.name,) if place.name != rule.name else ()
        return dataclasses.replace(
            place, name=rule.name, aliases=_merge(place.aliases, old, rule.aliases)
        ), rule.origin

    if state.map_places(renamed):
        state.names_changed = rule.origin


def _label(state, entry, lat, lon):
    rule = entry.rule
    if not _in_area(rule.within, entry, state, lat, lon):
        return
    for name, value in sorted(rule.fields.items(), key=lambda kv: kv[0] == "label"):  # label text last
        if name == "label":
            state.fields["label"] = value
            state.label_set = True
            state.mark("label", rule.origin)
        elif name == "region":
            region = Place(_synthetic_id(rule.origin, value, "region"), value, PlaceKind.REGION)
            state.fields["regions"] = [region, *(r for r in state.fields["regions"] if r.id != region.id)]
            state.mark("regions", rule.origin)
        else:
            current = state.fields[name]
            if current is None:
                state.fields[name] = Place(_synthetic_id(rule.origin, value, name), value, _FIELD_KIND[name])
            elif current.name != value:
                aliases = _merge(current.aliases, (current.name,))
                state.fields[name] = dataclasses.replace(current, name=value, aliases=aliases)
            else:
                continue
            state.mark(name, rule.origin)
            state.names_changed = rule.origin


def _city(state, entry, lat, lon):
    rule = entry.rule
    if rule.within is not None:
        hit = _in_area(rule.within, entry, state, lat, lon)
    else:
        locality = state.fields["locality"]
        hit = locality is not None and locality.id == rule.locality
    if not hit:
        return
    current = state.fields["city"]
    if current is not None and current.name == rule.city:
        return
    kind = current.kind if current is not None else PlaceKind.LOCALITY
    state.fields["city"] = Place(_synthetic_id(rule.origin, rule.city), rule.city, kind)
    state.mark("city", rule.origin)
    state.names_changed = rule.origin


def _region(state, entry, lat, lon):
    rule = entry.rule
    regions = state.fields["regions"]
    at = next((i for i, r in enumerate(regions) if r.id == rule.id), None)
    member = not rule.remove and _region_member(rule, entry, state, lat, lon)
    if not member:
        if at is not None:
            del regions[at]
            state.mark("regions", rule.origin)
        return
    current = regions[at] if at is not None else None
    if current is None:
        region = Place(rule.id, rule.label or rule.id, PlaceKind.REGION, aliases=rule.aliases)
        regions.append(region)
    else:
        region = dataclasses.replace(
            current, name=rule.label or current.name, aliases=_merge(current.aliases, rule.aliases)
        )
        if region == current:
            return
        regions[at] = region
    state.mark("regions", rule.origin)


def _region_member(rule, entry, state, lat, lon):
    places = [p for name in PLACE_FIELDS if (p := state.fields[name]) is not None]
    for key, codes in rule.members.items():
        for place in places:
            value = place.id if key == "id" else place.codes.get(key)
            if value is not None and value in codes:
                return True
    if rule.polygon is not None:
        return _in_area(AreaSelector(geojson=rule.polygon), entry, state, lat, lon)
    return False


def _hide(state, entry, lat, lon):
    rule = entry.rule
    for name in LIST_FIELDS:
        kept = [p for p in state.fields[name] if p.id != rule.id]
        if len(kept) != len(state.fields[name]):
            state.fields[name] = kept
            state.mark(name, rule.origin)
    kept = [n for n in state.fields["near"] if n.place.id != rule.id]
    if len(kept) != len(state.fields["near"]):
        state.fields["near"] = kept
        state.mark("near", rule.origin)
    for name in NEARBY_FIELDS:
        if (n := state.fields[name]) is not None and n.place.id == rule.id:
            state.fields[name] = None
            state.mark(name, rule.origin)


def _add(state, entry, lat, lon):
    rule = entry.rule
    distance = float(haversine(rule.point.lat, rule.point.lon, lat, lon))
    if rule.within is not None:
        hit = _in_area(rule.within, entry, state, lat, lon)
    else:
        hit = distance <= rule.radius_m / 1000.0
    if not hit:
        return
    place = Place(rule.id or _synthetic_id(rule.origin, rule.name), rule.name, rule.kind, point=rule.point)
    if rule.kind is PlaceKind.AIRPORT:
        state.fields["airport"] = Nearby(place, Relation.AT, distance)
        field = "airport"
    elif rule.kind is PlaceKind.WATER:
        state.fields["water"] = Nearby(place, Relation.OVER, distance)
        field = "water"
    else:
        field = "regions" if rule.kind is PlaceKind.REGION else "within"
        state.fields[field] = [place, *(p for p in state.fields[field] if p.id != place.id)]
    state.mark(field, rule.origin)
    near = [n for n in state.fields["near"] if n.place.id != place.id]  # it's here now, not near
    if len(near) != len(state.fields["near"]):
        state.fields["near"] = near
        state.mark("near", rule.origin)


_HANDLERS = {
    Rename: _rename,
    Label: _label,
    CityRule: _city,
    RegionRule: _region,
    Hide: _hide,
    Add: _add,
    # Alias rules only affect forward search (resolve_name); Tune is merged in _apply_tuning
}


# --- helpers ------------------------------------------------------------------------------------


def _in_area(area, entry, state, lat, lon):
    return area.matches(lat, lon, cc=state.cc, place_ids=state.place_ids, base_dir=entry.base_dir)


def _tag(origin):
    return f"{const.SOURCE_PREFIX}:{origin}" if origin else const.SOURCE_PREFIX


def _synthetic_id(origin, name, field=None):
    """Id for a place a rule creates: cites the rule, so apps grouping by id can trace it."""
    base = origin or "-".join(name.casefold().split())
    return f"{const.SOURCE_PREFIX}:{base}" + (f"/{field}" if field else "")


def _merge(*groups):
    out = []
    for group in groups:
        out.extend(name for name in group if name not in out)
    return tuple(out)


def _with_place(nearby, place):
    return nearby if place is nearby.place else dataclasses.replace(nearby, place=place)


def _norm(text):
    return " ".join(str(text).casefold().split())


def _alias_applies(rule, country, near):
    if rule.country and country and rule.country.upper() != country.upper():
        return False
    if rule.near is not None and near is not None:
        lat, lon = (near.lat, near.lon) if hasattr(near, "lat") else near
        return float(haversine(rule.near.lat, rule.near.lon, lat, lon)) <= const.ALIAS_NEAR_KM
    return True


# --- loading ------------------------------------------------------------------------------------


def load_overrides(repo_dir=None, local_path=None, app_rules=None, *, settings=None):
    """The override engine for this install.

    repo_dir:   directory of shipped rule files (default: placewise/overrides/repo); must exist.
    local_path: the user's file (default: the data directory's overrides.toml, or its .json twin,
                if present); False skips the local layer; a path given explicitly must exist.
    app_rules:  rules from the calling app: one document dict, an OverrideSet, or a list of them.
    settings:   Settings whose data.data_dir locates the default local file.
    """
    sets = []
    repo = REPO_DIR if repo_dir is None else Path(repo_dir)
    if not repo.is_dir():
        raise FileNotFoundError(f"overrides repo directory not found: {repo}")
    for path, cited in _repo_files(repo):
        sets.append((_read_set(Layer.REPO, path, f"repo:{cited}"), path.parent))

    if app_rules is not None:
        items = app_rules if isinstance(app_rules, list | tuple) else [app_rules]
        for i, item in enumerate(items, 1):
            if isinstance(item, OverrideSet):
                sets.append(item)
            else:
                sets.append(OverrideSet.from_dict(Layer.APP, item, "app" if len(items) == 1 else f"app:{i}"))

    local = _local_file(local_path, settings)
    if local is not None:
        sets.append((_read_set(Layer.LOCAL, local, f"local:{local.name}"), local.parent))
    return OverrideEngine(sets)


def _repo_files(directory):
    """(file to read, name to cite) per rule file. A .toml with a .json twin reads the twin where
    TOML can't be read (3.10 without tomli) but is cited as the .toml either way."""
    stems = sorted({p.stem for p in directory.iterdir() if p.is_file() and p.suffix in const.FILE_SUFFIXES})
    have_toml = _toml.available()
    out = []
    for stem in stems:
        toml, json = directory / f"{stem}.toml", directory / f"{stem}.json"
        if toml.exists():
            out.append((toml if have_toml or not json.exists() else json, toml.name))
        else:
            out.append((json, json.name))
    return out


def _local_file(local_path, settings):
    if local_path is False:
        return None
    if local_path is not None:
        path = Path(local_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"local overrides file not found: {path}")
        return path
    from placewise.store.paths import Layout, resolve_data_dir

    path = Layout(resolve_data_dir(settings=settings.data if settings is not None else None)).overrides
    for candidate in (path, path.with_suffix(".json")):
        if candidate.is_file():
            return candidate
    return None


def _read_set(layer, path, origin):
    try:
        doc = _toml.load(path)
    except _toml.TomlUnavailableError:
        raise
    except ValueError as e:
        raise ValueError(f"{origin}: {e}") from None
    try:
        return OverrideSet.from_dict(layer, doc, origin)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None
