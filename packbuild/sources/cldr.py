"""Unicode CLDR (cldr-json packages): per-territory conventions for the country profiles.

Readers for the supplemental files (measurement system, first day of the week, likely locales),
English currency names and symbols, and a locale's short date pattern. Territory tables fall back
to CLDR's world default, territory "001", as CLDR itself does.
"""

import json
from pathlib import Path

WORLD = "001"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _supplemental(path, name):
    return _load(path)["supplemental"][name]


def _by_territory(table):
    """{territory: value}, without CLDR's "-alt-variant" entries."""
    return {k: v for k, v in table.items() if "-alt-" not in k}


def measurement_systems(path):
    """{territory: "metric" | "US" | "UK"} from measurementData.json, with "001" the default."""
    return _by_territory(_supplemental(path, "measurementData")["measurementSystem"])


def first_days(path):
    """{territory: "mon" | "sun" | "sat" | "fri"} from weekData.json, with "001" the default."""
    return _by_territory(_supplemental(path, "weekData")["firstDay"])


def likely_subtags(path):
    """{"und-CA": "en-Latn-CA", "sr": "sr-Cyrl-RS", ...} from likelySubtags.json."""
    return dict(_supplemental(path, "likelySubtags"))


def available_locales(path):
    """The locales the cldr-*-full packages carry, from availableLocales.json."""
    return frozenset(_load(path)["availableLocales"]["full"])


def currencies(path):
    """{code: (English name, symbol, narrow symbol or None)} from main/en/currencies.json."""
    table = _load(path)["main"]["en"]["numbers"]["currencies"]
    return {
        code: (entry.get("displayName"), entry.get("symbol"), entry.get("symbol-alt-narrow"))
        for code, entry in table.items()
    }


def territory_locale(territory, likely, available):
    """The CLDR locale of a territory's likely main language ("en-CA", "de", "es-PR"), or None.

    likelySubtags gives "und-XX" for most territories; for the rest CLDR's own rule applies (the
    default "und" language with region XX), taken only when CLDR publishes a locale for that region,
    so a territory CLDR knows nothing about (AQ, HM) gets None rather than the default's conventions.
    """
    tag = likely.get(f"und-{territory}")
    if tag:
        return None if tag.startswith("und") else locale_for(tag, available, likely)
    default = likely.get("und", "")
    language, script, region = _parts(default)
    if region == territory:
        return locale_for(default, available, likely)
    candidates = (f"{language}-{script}-{territory}", f"{language}-{territory}")
    return next((c for c in candidates if c in available), None)


def _parts(tag):
    """(language, script, region) of a full tag, "" for what it lacks."""
    return tuple([*tag.split("-"), "", ""][:3])


def locale_for(tag, available, likely=None):
    """The closest locale CLDR publishes for a full tag (language-Script-REGION): the tag itself,
    language-REGION, language-Script, or the bare language when Script is its default script."""
    if not tag or tag.startswith("und"):
        return None
    language, script, region = _parts(tag)
    for candidate in (tag, f"{language}-{region}", f"{language}-{script}"):
        if candidate in available:
            return candidate
    default_script = _parts((likely or {}).get(language, ""))[1]
    if language in available and (likely is None or default_script == script):
        return language
    return None


def short_date(path, locale):
    """The short date pattern ("y-MM-dd") of a locale's ca-gregorian.json."""
    calendars = _load(path)["main"][locale]["dates"]["calendars"]
    return calendars["gregorian"]["dateFormats"]["short"]


def current_currencies(path):
    """{territory: ISO 4217 code} from currencyData.json: the first currency CLDR lists for the
    territory that is legal tender and has no end date (CLDR lists the most used first). Territories
    with none (AQ has only "XXX", no currency) are left out."""
    found = {}
    for territory, entries in _supplemental(path, "currencyData")["region"].items():
        for entry in entries:
            ((code, about),) = entry.items()
            if "_to" not in about and about.get("_tender") != "false" and code != "XXX":
                found[territory] = code
                break
    return found
