"""A tiny world pack holding only a country_facts layer, written the way packbuild writes it, with
values copied from the real sources for five countries (Antarctica as the one with gaps)."""

from packbuild.country_profiles import layer
from placewise.packs import write_pack

CREATED = "2026-11-17T00:00:00Z"
_EMPTY = dict.fromkeys(
    ("currency", "currency_name", "currency_symbol", "currency_narrow_symbol", "calling_code", "locale",
     "date_format", "driving_side", "postal_code_format", "postal_code_regex", "population_year"),
)  # fmt: skip


def _facts(name, iso3, **values):
    row = {**_EMPTY, "name": name, "iso3": iso3, "capital": None, "continent": None, "languages": ()}
    row |= {"measurement_system": "metric", "first_day_of_week": "monday", "tld": None, "time_zones": ()}
    row |= {"population": None, "area_km2": None, "neighbours": ()}
    return row | values


FACTS = {
    "CA": _facts(
        "Canada",
        "CAN",
        capital="Ottawa",
        continent="North America",
        currency="CAD",
        currency_name="Canadian Dollar",
        currency_symbol="CA$",
        currency_narrow_symbol="$",
        calling_code="+1",
        languages=("en-CA", "fr-CA", "iu"),
        first_day_of_week="sunday",
        locale="en-CA",
        date_format="y-MM-dd",
        driving_side="right",
        tld=".ca",
        time_zones=("America/St_Johns", "America/Toronto", "America/Vancouver"),
        population=41651653,
        area_km2=9984670,
        neighbours=("US",),
        postal_code_format="@#@ #@#",
    ),
    "US": _facts(
        "United States",
        "USA",
        capital="Washington",
        continent="North America",
        currency="USD",
        currency_name="US Dollar",
        currency_symbol="$",
        currency_narrow_symbol="$",
        calling_code="+1",
        languages=("en-US", "es-US"),
        measurement_system="US",
        first_day_of_week="sunday",
        locale="en",
        date_format="M/d/yy",
        driving_side="right",
        tld=".us",
        time_zones=("America/New_York",),
        population=341784857,
        area_km2=9629091,
        neighbours=("CA", "MX", "CU"),
    ),
    "GB": _facts(
        "United Kingdom",
        "GBR",
        capital="London",
        continent="Europe",
        currency="GBP",
        currency_name="British Pound",
        currency_symbol="£",
        currency_narrow_symbol="£",
        calling_code="+44",
        languages=("en-GB", "cy-GB", "gd"),
        measurement_system="imperial-mixed",
        locale="en-GB",
        date_format="dd/MM/y",
        driving_side="left",
        tld=".uk",
        time_zones=("Europe/London",),
        population=69487000,
        area_km2=244820,
        neighbours=("IE",),
    ),
    "IN": _facts(
        "India",
        "IND",
        capital="New Delhi",
        continent="Asia",
        currency="INR",
        currency_name="Indian Rupee",
        currency_symbol="₹",
        currency_narrow_symbol="₹",
        calling_code="+91",
        languages=("en-IN", "hi"),
        first_day_of_week="sunday",
        locale="hi",
        date_format="d/M/yy",
        driving_side="left",
        tld=".in",
        time_zones=("Asia/Kolkata",),
        population=1463865525,
        area_km2=3287590,
    ),
    "AQ": _facts("Antarctica", "ATA", continent="Antarctica", tld=".aq", population=0, area_km2=14000000),
}
CAPITALS = {"CA": (45.41, -75.70), "US": (38.90, -77.04), "GB": (51.51, -0.13), "IN": (28.61, 77.21)}
LABELS = {"AQ": (-80.0, 0.0)}


def write_world(out_dir, layers=None):
    """`<out_dir>/world-2026.11`, holding the country_facts layer (or the given layers)."""
    return write_pack(
        out_dir, "world", "2026.11", layers or [layer(FACTS, CAPITALS, LABELS)], created=CREATED
    )
