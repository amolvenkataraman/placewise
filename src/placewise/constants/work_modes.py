"""Remote, hybrid and onsite: the phrases that decide a work mode.

A source's own value ("OnSite", "REMOTE", True) wins; otherwise a description decides by
statements about the role itself, since a bare "remote" or "hybrid" isn't enough ("remote teams",
"remote sensing", "hybrid bonding"). Order: a hybrid statement, then a remote statement (both read
after DESCRIPTION_NEGATED phrases are removed, so "Hybrid or remote work will not be considered" isn't remote),
then a location naming Remote, then an onsite statement (read on the full text, so "This is not a
remote position" counts), then a location naming Hybrid. Patterns are case-insensitive regular
expressions. The LOCATION_* phrases read location strings ("Remote - US", "Hybrid (3 days/week)",
"In office 3 days/week"), where a bare "Remote" is enough.
"""

# ruff: noqa: E501  (the patterns are kept one per line)

REMOTE = "remote"
HYBRID = "hybrid"
ONSITE = "onsite"
MODES = (REMOTE, HYBRID, ONSITE)  # most permissive first: the order a location's mode is picked by

# --- Location strings (regular-expression fragments, case-insensitive) ---------------------------

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
LOCATION_DAY_COUNT = r"(?:[1-5]|one|two|three|four|five)"
LOCATION_IN_OFFICE = r"(?:in[- ]?office|in[- ]person|on[- ]?site|in\s+the\s+office|at\s+the\s+office)"
LOCATION_WEEKDAY = r"(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri)(?:days?)?"
LOCATION_NEGATED_REMOTE = (r"\bnon[- ]?remote\b", r"\bno[- ]remote\b", r"\bnot\s+remote\b")
LOCATION_HYBRID = (r"\bhybrid(?:[- ]remote)?\b", r"\bremote[- ]hybrid\b")
LOCATION_REMOTE = (
    r"(?:\b100%\s*|\bfully[- ])?\bremote\b(?:[- ](?:first|friendly|ok|only|eligible)\b)?",
    r"\bwfh\b",
    r"\bwork(?:ing)?[- ](?:from|at)[- ]home\b",
    r"\btele(?:commut|work)\w*",
    r"\bvirtual\b",
    r"\bdistributed\b",
    r"\banywhere\b",
    r"\bhome[- ]based\b",
)
LOCATION_ONSITE = (
    r"(?:\b100%\s*|\bfully\s+)?\bon[- ]?site\b",
    r"(?:\bfully\s+)?\bin[- ]office\b",
    r"\bin[- ]person\b",
    r"\boffice[- ]based\b",
    r"\bin\s+the\s+office\b",
)

# --- A source's own value and descriptions ------------------------------------------------------

# a source's own value, lower-cased with non-letters as spaces ("ON_SITE" -> "on site"), including
# the snake-case spellings some feeds use ("remote_local", "on_site")
STRUCTURED = {
    "remote": ("remote", "fully remote", "telecommute", "work from home", "virtual", "remote local"),
    "hybrid": ("hybrid", "flexible"),
    "onsite": (
        "onsite",
        "on-site",
        "on site",
        "in office",
        "in-office",
        "in_office",
        "office",
        "in person",
        "in-person",
    ),
}

DESCRIPTION_NEGATED = (
    "\\b(?:not|never|no)\\s+(?:an?\\s+|be\\s+)?(?:fully\\s+)?remote\\b",
    "\\bnon[- ]remote\\b",
    "\\b(?:hybrid\\s+(?:or|and|/)\\s+)?remote(?:\\s+(?:or|and|/)\\s+hybrid)?\\s+(?:work\\s+|working\\s+)?(?:options?\\s+|arrangements?\\s+|roles?\\s+|positions?\\s+)?(?:will\\s+not|won't|is\\s+not|are\\s+not|isn't|aren't|cannot|can\\s?not|can't|not)\\s+(?:be\\s+)?(?:considered|available|offered|possible|permitted|supported|allowed|accommodated|guaranteed)",
)

DESCRIPTION_HYBRID = (
    "#li-hybrid\\b",
    "\\bhybrid[- ](?:work|working|workplace|schedule|model|policy|arrangement|environment|setup|basis)\\b",
    "\\b(?:this|the|our|is\\s+an?|will\\s+be\\s+an?|as\\s+an?)\\s+(?:\\w+\\s+){0,2}hybrid\\s+(?:on-?site\\s+)?(?:role|position|opportunity|internship|co-?op)\\b",
    "\\bdesign(?:ed|ated)\\s+as\\s*['‘’\"“”]*\\s*hybrid\\b",
    "\\(hybrid\\)",
    "(?:office|on-?site|in[- ]person)[^.\\n]{0,80}?\\b(?:[1-4]|one|two|three|four)(?:\\s*\\([1-4]\\))?(?:\\s*(?:-|to|or)\\s*(?:[1-5]|two|three|four|five))?\\s+days?\\s+(?:a|per|each|every)\\s+week\\b",
    "\\b(?:[1-4]|one|two|three|four)(?:\\s*\\([1-4]\\))?(?:\\s*(?:-|to|or)\\s*(?:[1-5]|two|three|four|five))?\\s+days?\\s+(?:a|per|each|every)\\s+week\\b[^.\\n]{0,60}?(?:office|on-?site|in[- ]person)",
    "\\b[1-9]\\d?%\\s+telecommut",
    "\\b(?:roles?|positions?|internships?)\\s+(?:are|is)\\s+(?:all\\s+)?hybrid\\b",
    "\\bwork\\s+(?:location|model|arrangement|type|style)\\s*:?\\s*hybrid\\b",
    "·\\s*hybrid\\b",
    "\\b(?:on-?site|in[- ]office|in\\s+the\\s+office)\\s+(?:on\\s+)?(?:mon|tues|wednes|thurs|fri)days?,?\\s+(?:and\\s+)?(?:mon|tues|wednes|thurs|fri)days?\\b",
)

DESCRIPTION_REMOTE = (
    "#li-remote\\b",
    "\\bfully[- ]remote\\b",
    "\\b100%\\s+(?:remote|telecommut)",
    "\\bremote[- ]first\\b",
    "\\b(?:this|the)\\s+(?:role|position|opportunity)\\s+is\\s+(?:currently\\s+|a\\s+)?(?:fully\\s+)?remote\\b",
    "\\b(?:position|role)\\s+is\\s+currently\\s+remote\\b",
    "\\bthis\\s+is\\s+an?\\s+(?:fully\\s+|100%\\s+)?remote\\s+(?:position|role|opportunity)\\b",
    "\\bremote\\s*/\\s*telework(?:er)?\\b",
    "\\bdesign(?:ed|ated)\\s+as\\s*['‘’\"“”]*\\s*remote\\b",
    "\\bwork[- ]at[- ]home\\b",
    "\\bprimarily\\s+work\\s+from\\s+home\\b",
    "\\bwork\\s+from\\s+anywhere\\b",
    "\\bwork\\s+remotely\\s+from\\s+(?:anywhere|any\\b|the\\s+(?:us|u\\.s\\.|united\\s+states|uk|united\\s+kingdom|eu))",
    "\\bwork\\s+(?:location|model|arrangement|type|style)\\s*:?\\s*(?:fully\\s+)?remote\\b",
    "·\\s*remote\\b",
)

DESCRIPTION_ONSITE = (
    "#li-onsite\\b",
    "\\b(?:100%|fully|full[- ]time,?)\\s+on-?site\\b",
    "\\bon-?site\\s+(?:presence|role|position|only|internship|requirement)\\b",
    "\\b(?:position|role)\\s+is\\s+(?:located\\s+|based\\s+)?on-?site\\b",
    "\\bwork(?:ing)?\\s+(?:full[- ]time\\s+)?on-?site\\s+(?:at|in)\\b",
    "\\brole\\s+type:?\\s*on-?site\\b",
    "\\bclassified\\s+as:?\\s*on-?site\\b",
    "\\bdesign(?:ed|ated)\\s+as\\s*['‘’\"“”]*\\s*on-?site\\b",
    "\\((?:on-?site|in[- ]office)\\)",
    "\\bnot\\s+an?\\s+(?:fully\\s+)?remote\\s+(?:position|role|opportunity)\\b",
    "\\b(?:hybrid\\s+(?:or|and|/)\\s+)?remote(?:\\s+(?:or|and|/)\\s+hybrid)?\\s+(?:work\\s+|working\\s+)?(?:options?\\s+|arrangements?\\s+)?(?:will\\s+not|won't|is\\s+not|are\\s+not|cannot|not)\\s+(?:be\\s+)?(?:considered|available|offered|possible)",
    "\\bwork\\s+from\\s+(?:the|our|an?)\\s+office\\s+full[- ]time\\b",
    "\\bin[- ]office\\s+(?:role|position|full[- ]time)\\b",
    "\\b(?:five|5)\\s+days\\s+(?:a|per|each)\\s+week\\s+in\\s+(?:the\\s+|our\\s+)?office\\b",
    "\\b(?:positions?|roles?)\\s+(?:at\\s+(?:\\w+\\s+){1,4})?(?:is|are)\\s+(?:full[- ]time\\s+)?on-?site\\b",
    "\\b(?:must\\s+be\\s+(?:able|available|willing)|ability)\\s+to\\s+(?:perform\\s+)?work\\s+on-?site\\b",
    "\\brequires?\\s+(?:daily|full[- ]time)\\s+on-?site\\b",
    "\\b(?:location|role|position|internship)\\s+(?:will\\s+be|is)\\s+(?:located\\s+|based\\s+|fully\\s+|100%\\s+)?on-?site\\b",
    "\\bon-?site\\s+at\\s+our\\b",
    "·\\s*on-?site\\b",
    "\\b(?:5|five)\\s+days\\s+(?:a\\s+week\\s+|per\\s+week\\s+)?on-?site\\b",
    "\\bon-?site\\s+(?:5|five)\\s+days\\b",
    "\\bwork\\s+(?:location|model|arrangement|type|style)\\s*:?\\s*on-?site\\b",
    "\\bfull[- ]time,?\\s+in[- ]person\\b",
)
