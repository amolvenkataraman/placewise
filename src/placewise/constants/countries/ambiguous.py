"""Names that mean more than one place when nothing else in a location string settles it.

AMBIGUOUS_CITIES: a bare city name and its candidates, each with a rough prior weight for
location strings (summing to 1); a context country, another place in the same string, or a
gazetteer reorders or prunes them. NAME_CLASHES: names that are both a US state and a country.
"""

from ._records import Candidate, NameClash

AMBIGUOUS_CITIES = {
    "London": (Candidate("GB", "ENG", "England", 0.8), Candidate("CA", "ON", weight=0.2)),
    "Cambridge": (
        Candidate("GB", "ENG", "England", 0.5),
        Candidate("US", "MA", weight=0.4),
        Candidate("CA", "ON", weight=0.1),
    ),
    "Birmingham": (Candidate("GB", "ENG", "England", 0.6), Candidate("US", "AL", weight=0.4)),
    "Vancouver": (Candidate("CA", "BC", weight=0.8), Candidate("US", "WA", weight=0.2)),
    "Portland": (Candidate("US", "OR", weight=0.8), Candidate("US", "ME", weight=0.2)),
    "Dublin": (
        Candidate("IE", weight=0.8),
        Candidate("US", "OH", weight=0.1),
        Candidate("US", "CA", weight=0.1),
    ),
    "Perth": (Candidate("AU", "WA", "Western Australia", 0.8), Candidate("GB", "SCT", "Scotland", 0.2)),
    "Hyderabad": (Candidate("IN", "TS", weight=0.8), Candidate("PK", "SD", "Sindh", 0.2)),
    "Richmond": (Candidate("US", "VA", weight=0.5), Candidate("CA", "BC", weight=0.5)),
}

NAME_CLASHES = {
    "Georgia": NameClash("GA", "US", "GE", ("Tbilisi", "Batumi", "Kutaisi", "Rustavi", "Zugdidi")),
}
