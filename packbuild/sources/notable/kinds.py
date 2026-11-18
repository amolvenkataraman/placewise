"""The kind allowlist: which Wikidata classes make which kind of notable place, and the SPARQL
query that lists each kind's items.

One query per kind, run on QLever's Wikidata endpoint (WDQS times out on classes this big): items
that are instances of a root class or any subclass of one (`wdt:P31/wdt:P279*`), with a
coordinate (P625, best rank only), an English label and at least one sitelink, never dissolved,
demolished (P576) or closed (P3999). Each row carries the item, its label, one coordinate, the
sitelink count, its countries (P17's ISO alpha-2, `|`-joined), its English aliases (`|`-joined)
and the kind's external ids.

An item listed by several kinds takes the first in KINDS order (a tower that is also an
"architectural landmark" is a landmark; a cricket ground that is a park is a stadium). The registry
(`sources/notable.json`, downloads `notable_<kind>`) holds `url(kind)` for every kind; a test keeps
the two equal, so change the classes here and paste the new URL there.
"""

import urllib.parse
from dataclasses import dataclass

ENDPOINT = "https://qlever.dev/api/wikidata"

# external id properties by the column they fill (a column listing several takes the first found)
CODES = {
    "iata": ("P238",),
    "icao": ("P239",),
    "ipeds": ("P1771",),
    "aishe": ("P6392",),
    # Indian Railways, Amtrak, VIA Rail, then any station code
    "station_code": ("P5696", "P4803", "P10653", "P296"),
}


@dataclass(frozen=True)
class Kind:
    name: str
    roots: tuple[str, ...]  # classes whose instances (and their subclasses') are this kind
    codes: tuple[str, ...] = ()  # CODES columns read for this kind
    required: str | None = None  # a CODES column every item of the kind must have
    exclude: tuple[str, ...] = ()  # classes whose instances are left out


# monument, architectural landmark, tourist attraction, archaeological site, square, mausoleum,
# statue, memorial, intersection (Shibuya Crossing), waterfall
LANDMARK_ROOTS = ("Q4989906", "Q2319498", "Q570116", "Q839954", "Q174782", "Q162875", "Q179700", "Q5003624",
                  "Q285783", "Q34038")  # fmt: skip
# skyscraper, tower, castle, palace, lighthouse, fortification, opera house, concert hall, theatre
# building, shopping center
BUILDING_ROOTS = ("Q11303", "Q12518", "Q23413", "Q16560", "Q39715", "Q57821", "Q153562", "Q1060829", "Q24354",
                  "Q11315")  # fmt: skip

# priority order: an item in several kinds takes the first
KINDS = (
    Kind("airport", ("Q1248784",), codes=("iata", "icao"), required="iata"),  # scheduled: IATA code
    Kind("station", ("Q55488", "Q928830", "Q494829"), codes=("station_code",)),  # rail, metro, bus
    # higher education institution, not its faculties ("University of Waterloo Faculty of Mathematics")
    Kind("university", ("Q38723",), codes=("ipeds", "aishe"), exclude=("Q180958",)),
    Kind("campus", ("Q4819632", "Q123302448"), codes=("ipeds", "aishe")),  # satellite campus, campus
    Kind("stadium", ("Q483110", "Q641226", "Q682943")),  # stadium, arena, cricket field
    Kind("museum", ("Q33506",)),
    Kind("religious_site", ("Q1370598",)),  # structure of worship
    Kind("bridge", ("Q12280",)),
    # park, zoo, botanical garden, amusement park, garden; not protected areas (the park packs)
    Kind("park", ("Q22698", "Q43501", "Q167346", "Q194195", "Q1107656"), exclude=("Q473972",)),
    Kind("beach", ("Q40080",)),
    Kind("landmark", LANDMARK_ROOTS),
    # after landmark: observation towers are viewpoints too, but the Eiffel Tower is a landmark
    Kind("viewpoint", ("Q6017969",)),  # scenic viewpoint
    Kind("building", BUILDING_ROOTS),
)
BY_NAME = {k.name: k for k in KINDS}
PRIORITY = {k.name: i for i, k in enumerate(KINDS)}

_PREFIXES = (
    "PREFIX wd: <http://www.wikidata.org/entity/> "
    "PREFIX wdt: <http://www.wikidata.org/prop/direct/> "
    "PREFIX wikibase: <http://wikiba.se/ontology#> "
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
    "PREFIX skos: <http://www.w3.org/2004/02/skos/core#> "
)


def code_variables(kind):
    """[(SPARQL variable, property)] of a kind's external ids, in CODES order."""
    return [(f"{column}{i}", prop) for column in kind.codes for i, prop in enumerate(CODES[column])]


def query(kind):
    """The SPARQL text listing one kind's items (one line, so the URL stays readable)."""
    codes = code_variables(kind)
    select = " ".join(f"(MIN(?{v}_) AS ?{v})" for v, _ in codes)
    optional = " ".join(f"OPTIONAL {{ ?item wdt:{p} ?{v}_ }}" for v, p in codes)
    required = ""
    if kind.required:
        required = " ".join(f"?item wdt:{p} ?req{i} ." for i, p in enumerate(CODES[kind.required][:1]))
    exclude = " ".join(f"MINUS {{ ?item wdt:P31/wdt:P279* wd:{q} }}" for q in kind.exclude)
    roots = " ".join(f"wd:{q}" for q in kind.roots)
    parts = [
        _PREFIXES,
        "SELECT ?item ?label (SAMPLE(?coord) AS ?point) ?sitelinks",
        '(GROUP_CONCAT(DISTINCT ?cc; SEPARATOR="|") AS ?countries)',
        '(GROUP_CONCAT(DISTINCT ?alias; SEPARATOR="|") AS ?aliases)',
        select,
        f"WHERE {{ VALUES ?root {{ {roots} }} ?item wdt:P31/wdt:P279* ?root .",
        "?item wdt:P625 ?coord ; wikibase:sitelinks ?sitelinks ; rdfs:label ?label .",
        'FILTER(LANG(?label) = "en") FILTER(?sitelinks >= 1)',
        required,
        "MINUS { ?item wdt:P576 ?end } MINUS { ?item wdt:P3999 ?closed }",
        exclude,
        "OPTIONAL { ?item wdt:P17/wdt:P297 ?cc }",
        'OPTIONAL { ?item skos:altLabel ?alias FILTER(LANG(?alias) = "en") }',
        optional,
        "} GROUP BY ?item ?label ?sitelinks",
    ]
    return " ".join(p.strip() for p in parts if p.strip())


def url(kind):
    """The registry download URL of a kind's query: QLever's TSV export."""
    return f"{ENDPOINT}?action=tsv_export&query={urllib.parse.quote(query(kind), safe='')}"


def download_name(kind):
    return f"notable_{kind.name}"
