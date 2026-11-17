import random
import re

import pytest

from placewise.text.parse import patterns
from placewise.text.parse.patterns import _none_of, _Prefiltered, _prefiltered, _required, _sre_parse


def required(pattern, flags=re.IGNORECASE):
    return _required(list(_sre_parse.parse(pattern, flags)))


@pytest.mark.parametrize(
    ("pattern", "words"),
    [
        (r"\bremote\b", ("remote",)),
        (r"(?:\bfully[- ])?\bremote\b", ("remote",)),  # an optional prefix proves nothing
        (r"\bwfh\b|\bvirtual\b", ("wfh", "virtual")),
        (r"\bwork(?:ing)?[- ]home\b", ("work",)),
        (r"\bOn[- ]?Site\b", ("site",)),  # lower case, the longest literal run
        (r"\d{5}", tuple("0123456789")),
        (r"[1-9]\d", tuple("123456789")),
        (r"(?:abc)+x", ("abc",)),
        (r"a|\w+", None),  # an arm that needs no literal
        (r"(?:abc)*", None),
        (r"\w+", None),
        (r"café", ("caf",)),  # only ASCII literals count
    ],
)
def test_required_strings(pattern, words):
    assert required(pattern) == words


ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,-/&+;|()%:.éK"
WORDS = (
    "remote", "Remote", "hybrid", "on-site", "onsite", "in office", "3 days/week", "wfh", "work from home",
    "Toronto", "ON", "or", "and", "Greater", "Area", "HQ", "Suite 100", "+ 3 more", "multiple locations",
    "94105", "M5V 2T6", "560001", "north east", "the", "in", "tbd", "n/a", "telework", "100% remote",
)  # fmt: skip


def strings(n=3000, seed=1):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        parts = [rng.choice(WORDS) if rng.random() < 0.7 else "".join(rng.choices(ALPHABET, k=4))]
        parts += [rng.choice(WORDS) for _ in range(rng.randrange(4))]
        out.append(rng.choice((" ", ", ", " - ", "")).join(parts))
    return out


PREFILTERED = [(name, value) for name, value in vars(patterns).items() if isinstance(value, _Prefiltered)] + [
    (f"POSTAL_CODES[{i}]", p) for i, p in enumerate(patterns.POSTAL_CODES)
]


@pytest.mark.parametrize(("name", "pattern"), PREFILTERED, ids=[name for name, _ in PREFILTERED])
def test_prefiltered_patterns_answer_like_the_regex(name, pattern):
    if pattern.words is None:  # a combined prefilter has nothing of its own to compare
        return
    regex = pattern.regex
    for text in strings():
        assert [m.span() for m in pattern.finditer(text)] == [m.span() for m in regex.finditer(text)], text
        assert pattern.findall(text) == regex.findall(text)
        assert bool(pattern.search(text)) == bool(regex.search(text))
        assert bool(pattern.match(text)) == bool(regex.match(text))
        assert pattern.sub("_", text) == regex.sub("_", text)


def test_combined_prefilter_is_hopeless_only_when_every_pattern_is():
    members = (patterns.REMOTE, patterns.HYBRID, patterns.ONSITE)
    combined = _none_of(*members)
    texts = strings()
    assert any(combined.hopeless(text) for text in texts)
    for text in texts:
        if combined.hopeless(text):
            assert all(not m.regex.search(text) for m in members)


def test_non_ascii_text_always_runs_the_regex():
    # the Kelvin sign matches "k" when case is ignored, which a lower-case substring test would miss
    pattern = _prefiltered(re.compile(r"\bwork\b", re.IGNORECASE))
    assert pattern.words == ("work",)
    assert pattern.search("worK")


def test_patterns_without_a_requirement_stay_plain_regexes():
    assert isinstance(patterns.LEADING, re.Pattern)
    assert isinstance(patterns.PARENS, re.Pattern)
