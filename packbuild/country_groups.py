"""Country groups: validate the curated datasets in datasets/country_groups/ and generate the offline copy
the package reads, src/placewise/constants/countries/groups.py.

    uv run python -m packbuild.country_groups            # validate, then write the module
    uv run python -m packbuild.country_groups --check    # validate, and fail if the module is stale

ISO 3166-1 alpha-2 codes are checked against the package's full ISO table
(`placewise.constants.countries.BY_ALPHA2`, all 249 assigned codes).
"""

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
DATASETS = REPO / "datasets" / "country_groups"
MODULE = REPO / "src" / "placewise" / "constants" / "countries" / "groups.py"

GEOGRAPHIC_KINDS = frozenset({"continent", "un-m49-region", "un-m49-subregion", "custom", "business"})
LEGAL_KINDS = frozenset(
    {"union", "treaty-area", "currency-union", "trade-agreement", "alliance", "forum", "intergovernmental"}
)
GROUP_KEYS = frozenset({"id", "name", "aliases", "kind", "members", "source", "notes"})
OPTIONAL_GROUP_KEYS = frozenset({"other_sources"})
MEMBER_REFS = ("code", "group", "entity")  # exactly one per legal member
MEMBER_KEYS = frozenset({*MEMBER_REFS, "since", "until", "suspended_since", "note"})
DATE_KEYS = ("since", "until", "suspended_since")

_DATE = re.compile(r"\d{4}(-\d{2}-\d{2})?")
_WIDTH = 110


def iso_alpha2():
    """Every assigned ISO 3166-1 alpha-2 code, from the package's country table."""
    from placewise.constants.countries import BY_ALPHA2

    return frozenset(BY_ALPHA2)


def load(datasets=DATASETS):
    """(geographic, legal): the two dataset files as parsed JSON."""
    datasets = Path(datasets)
    return tuple(
        json.loads((datasets / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("geographic", "legal")
    )


# --- validation ---


def _date_error(value):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return f"bad date {value!r} (YYYY or YYYY-MM-DD)"
    if len(value) == 10:
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            return f"bad date {value!r} (no such day)"
    return None


def _source_ok(source):
    """An official https URL, or "convention" for groupings no body defines."""
    if not isinstance(source, str):
        return False
    parts = urlsplit(source)
    return source == "convention" or (parts.scheme == "https" and bool(parts.netloc))


def _check_group(group, prefix, kinds, errors):
    gid = group.get("id", "?")
    missing = GROUP_KEYS - group.keys()
    extra = group.keys() - GROUP_KEYS - OPTIONAL_GROUP_KEYS
    if missing:
        errors.append(f"{gid}: missing {sorted(missing)}")
    if extra:
        errors.append(f"{gid}: unknown keys {sorted(extra)}")
    if not str(gid).startswith(prefix):
        errors.append(f"{gid}: id must start with {prefix!r}")
    if group.get("kind") not in kinds:
        errors.append(f"{gid}: kind {group.get('kind')!r} not one of {sorted(kinds)}")
    if not _source_ok(group.get("source")):
        errors.append(f"{gid}: source must be an https:// URL or 'convention'")
    if not all(_source_ok(s) and s != "convention" for s in group.get("other_sources", [])):
        errors.append(f"{gid}: other_sources must be https:// URLs")
    if not isinstance(group.get("name"), str) or not group.get("name"):
        errors.append(f"{gid}: name must be a non-empty string")
    aliases = group.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(a, str) and a.strip() for a in aliases):
        errors.append(f"{gid}: aliases must be a list of non-empty strings")
    if not group.get("members"):
        errors.append(f"{gid}: no members")


def _check_codes(gid, codes, iso, errors):
    seen = set()
    for code in codes:
        if code not in iso:
            errors.append(f"{gid}: {code!r} is not an ISO 3166-1 alpha-2 code")
        if code in seen:
            errors.append(f"{gid}: duplicate member {code!r}")
        seen.add(code)


def _check_legal_member(gid, member, group_ids, errors):
    refs = [k for k in MEMBER_REFS if k in member]
    if len(refs) != 1:
        errors.append(f"{gid}: member {member} needs exactly one of {MEMBER_REFS}")
    if member.keys() - MEMBER_KEYS:
        errors.append(f"{gid}: member {member} has unknown keys {sorted(member.keys() - MEMBER_KEYS)}")
    if "group" in member and member["group"] not in group_ids:
        errors.append(f"{gid}: member refers to unknown group {member['group']!r}")
    for key in DATE_KEYS:
        if key in member and (problem := _date_error(member[key])):
            errors.append(
                f"{gid}: {member.get('code') or member.get('group') or member.get('entity')}: {problem}"
            )
    since, until = member.get("since"), member.get("until")
    if since and until and not _date_error(since) and not _date_error(until) and until < since:
        errors.append(f"{gid}: {member.get('code')}: until {until} is before since {since}")


def validate(geographic, legal, iso=None):
    """Every problem found in the two datasets, as readable strings; [] when they are valid."""
    iso = iso_alpha2() if iso is None else iso
    errors = []
    for name, data in (("geographic", geographic), ("legal", legal)):
        if _date_error(data.get("as_of")) or len(str(data.get("as_of"))) != 10:
            errors.append(f"{name}.json: as_of must be a YYYY-MM-DD date")
        if not isinstance(data.get("groups"), list):
            errors.append(f"{name}.json: groups must be a list")
            return errors
    groups = [*geographic["groups"], *legal["groups"]]
    group_ids = {g.get("id") for g in groups}

    seen_ids, owner = set(), {}
    for group in groups:
        gid = group.get("id")
        if gid in seen_ids:
            errors.append(f"duplicate id {gid!r}")
        seen_ids.add(gid)
        own = set()
        for alias in (group.get("name"), *group.get("aliases", [])):
            if not isinstance(alias, str):
                continue
            key = alias_key(alias)
            if key in own:
                errors.append(f"{gid}: alias {key!r} repeated")
            elif owner.setdefault(key, gid) != gid:
                errors.append(f"alias {key!r} used by both {owner[key]} and {gid}")
            own.add(key)

    for group in geographic["groups"]:
        _check_group(group, "geo:", GEOGRAPHIC_KINDS, errors)
        members = group.get("members", [])
        if not all(isinstance(c, str) for c in members):
            errors.append(f"{group.get('id')}: geographic members must be alpha-2 strings")
            continue
        _check_codes(group.get("id"), members, iso, errors)
    for group in legal["groups"]:
        gid = group.get("id")
        _check_group(group, "legal:", LEGAL_KINDS, errors)
        members = group.get("members", [])
        if not all(isinstance(m, dict) for m in members):
            errors.append(f"{gid}: legal members must be objects")
            continue
        for member in members:
            _check_legal_member(gid, member, group_ids, errors)
        refs = [m.get("code") or m.get("group") or m.get("entity") for m in members]
        _check_codes(gid, [m["code"] for m in members if "code" in m], iso, errors)
        if len(set(refs)) != len(refs):
            errors.append(f"{gid}: duplicate member among non-country entries")
    return errors


def alias_key(alias):
    """How an alias is looked up: lower case, outer space trimmed."""
    return alias.strip().lower()


# --- rendering ---


def _lit(value):
    """A Python literal for str / None / tuple of str, in double quotes."""
    if value is None:
        return "None"
    return json.dumps(value, ensure_ascii=False)


def _pack(items, indent):
    """Comma-separated items, wrapped to the line width, each line indented and ending in a comma."""
    pad, lines, line = " " * indent, [], ""
    for item in items:
        candidate = f"{line} {item}," if line else f"{item},"
        if line and len(pad) + len(candidate) > _WIDTH:
            lines.append(pad + line)
            candidate = f"{item},"
        line = candidate
    if line:
        lines.append(pad + line)
    return lines


def _tuple(values, indent):
    values = [_lit(v) for v in values]
    one = "(" + ", ".join(values) + ("," if len(values) == 1 else "") + ")"
    if indent + len(one) + 14 <= _WIDTH:
        return [one]
    return ["(", *_pack(values, indent + 4), " " * indent + ")"]


def _text(value, indent):
    """A string literal; a long one is split over lines (implicit concatenation in parentheses)."""
    one = _lit(value)
    if indent + len(one) + 12 <= _WIDTH or " " not in value:  # short, or one word (a URL)
        return [one]
    pad, chunks, chunk = " " * (indent + 4), [], ""
    for word in value.split(" "):
        piece = f"{chunk} {word}" if chunk else word
        if chunk and len(pad) + len(_lit(piece + " ")) > _WIDTH:
            chunks.append(chunk + " ")
            piece = word
        chunk = piece
    chunks.append(chunk)
    return ["(", *(pad + _lit(c) for c in chunks), " " * indent + ")"]


def _legal_member(member, indent):
    """Lines for one legal member: one line, or one per field when that would be too long."""
    fields = {"code": member.get("code"), "since": member.get("since"), "until": member.get("until")}
    for key in ("group", "entity", "suspended_since"):
        if key in member:
            fields[key] = member[key]
    pairs = [f"{_lit(k)}: {_lit(v)}" for k, v in fields.items()]
    pad = " " * indent
    one = pad + "{" + ", ".join(pairs) + "},"
    if len(one) <= _WIDTH:
        return [one]
    return [pad + "{", *(f"{pad}    {p}," for p in pairs), pad + "},"]


def _group_lines(group, legal):
    lines = [f"    {_lit(group['id'])}: {{", f'        "name": {_lit(group["name"])},']
    aliases = _tuple(group["aliases"], 8)
    lines.append(f'        "aliases": {aliases[0]}')
    lines += aliases[1:]
    lines[-1] += ","
    lines.append(f'        "kind": {_lit(group["kind"])},')
    if legal:
        lines.append('        "members": (')
        for member in group["members"]:
            lines += _legal_member(member, 12)
        lines.append("        ),")
    else:
        members = _tuple(group["members"], 8)
        lines.append(f'        "members": {members[0]}')
        lines += members[1:]
        lines[-1] += ","
    for key in ("source", "notes"):
        text = _text(group[key], 8)
        lines.append(f'        "{key}": {text[0]}')
        lines += text[1:]
        lines[-1] += ","
    lines.append("    },")
    return lines


def render(geographic, legal):
    """The text of the generated groups.py."""
    aliases = {}
    for group in (*geographic["groups"], *legal["groups"]):
        for alias in (group["name"], *group["aliases"]):
            aliases[alias_key(alias)] = group["id"]
    as_of = max(geographic["as_of"], legal["as_of"])
    out = [
        '"""GENERATED from datasets/country_groups by packbuild.country_groups; do not edit.',
        "",
        "Regenerate with `uv run python -m packbuild.country_groups`. Each group carries its source and",
        "notes; the reasoning behind single memberships (member notes, other sources) stays in the datasets.",
        '"""',
        "",
        "# fmt: off",
        "",
        "# date the memberships were checked against their sources",
        f"AS_OF = {_lit(as_of)}",
        "",
        "# id -> {name, aliases, kind, members, source, notes}; members are ISO 3166-1 alpha-2 codes",
        "GEOGRAPHIC = {",
    ]
    for group in geographic["groups"]:
        out += _group_lines(group, legal=False)
    out += [
        "}",
        "",
        "# id -> {name, aliases, kind, members, source, notes}; each member has code (alpha-2, or None for",
        "# a member without one, which then has `group` (an id here) or `entity` (a name)), since and",
        "# until (None when unknown or still a member), and suspended_since when the organisation has",
        "# suspended it",
        "LEGAL = {",
    ]
    for group in legal["groups"]:
        out += _group_lines(group, legal=True)
    out += ["}", "", "# lower-cased name or alias -> group id", "ALIASES = {"]
    out += _pack([f"{_lit(k)}: {_lit(v)}" for k, v in aliases.items()], 4)
    out += ["}", ""]
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--datasets", type=Path, default=DATASETS, help="folder holding the two JSON files")
    parser.add_argument("--out", type=Path, default=MODULE, help="module to write")
    parser.add_argument(
        "--check", action="store_true", help="fail if --out differs from what would be written"
    )
    args = parser.parse_args(argv)

    geographic, legal = load(args.datasets)
    errors = validate(geographic, legal)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    text = render(geographic, legal)
    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else None
        if current != text:
            print(f"{args.out} is stale: run python -m packbuild.country_groups", file=sys.stderr)
            return 1
        return 0
    args.out.write_text(text, encoding="utf-8")
    counts = (len(geographic["groups"]), len(legal["groups"]))
    print(f"wrote {args.out} ({counts[0]} geographic, {counts[1]} legal groups)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
