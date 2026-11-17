"""Country profiles: the world pack's country_facts layer (GeoNames, Unicode CLDR, Wikidata), read
lazily from the installed pack (through the store, as placewise.engine.Geocoder does) or from a
pack given explicitly."""

import functools
from pathlib import Path

from placewise.constants.world import FACTS_LAYER, INSTALL_HINT, PACK
from placewise.model import Currency, Profile, Statistic

from .countries import country as _country
from .subregions import subregion as _subregion

# facts that hold for every part of a country, so a subregion's profile carries them too
_COUNTRY_WIDE = (
    "continent", "currency", "calling_code", "measurement_system", "driving_side", "first_day_of_week",
    "date_format", "locale", "tld", "postal_code_format", "postal_code_regex",
)  # fmt: skip


def _read(pack):
    """{alpha-2: row} from an opened pack's country_facts layer."""
    if FACTS_LAYER not in pack:
        raise LookupError(
            f"the {pack.name} pack at {pack.path} has no {FACTS_LAYER} layer (it predates country "
            f"profiles); update it with: {INSTALL_HINT}"
        )
    layer = pack[FACTS_LAYER]
    return {layer.value("iso2", i): layer.row(i) for i in range(len(layer))}


@functools.lru_cache(maxsize=4)
def _from_path(path):
    from placewise.packs import open_pack

    return _read(open_pack(path))


def _installed(store):
    import placewise.config
    import placewise.store

    try:
        if store is None:  # placewise.toml and env decide where packs come from, as for lookup
            store = placewise.store.Store(settings=placewise.config.load_settings().data)
        return store.ensure(PACK)
    except (placewise.store.StoreError, OSError) as e:
        raise LookupError(
            f"country profiles read the {PACK} pack's {FACTS_LAYER} layer, and no {PACK} pack is "
            f"available ({e}); install it with: {INSTALL_HINT}"
        ) from None


def _facts(pack, store):
    from placewise.packs import Pack

    if isinstance(pack, Pack):
        return _read(pack)
    path = Path(pack) if pack is not None else Path(_installed(store))
    return _from_path(str(path.resolve()))


def _split(value):
    return tuple(v for v in value.split(",") if v) if value else ()


def _fields(row):
    """Profile fields from a country_facts row (nulls already None)."""
    currency = row["currency"]
    population, area = row["population"], row["area_km2"]
    return {
        "capital": row["capital"],
        "continent": row["continent"],
        "currency": Currency(
            currency, row["currency_name"], row["currency_symbol"], row["currency_narrow_symbol"]
        )
        if currency
        else None,
        "calling_code": row["calling_code"],
        "languages": _split(row["languages"]),
        "measurement_system": row["measurement_system"],
        "driving_side": row["driving_side"],
        "first_day_of_week": row["first_day_of_week"],
        "date_format": row["date_format"],
        "locale": row["locale"],
        "tld": row["tld"],
        "time_zones": _split(row["time_zones"]),
        "population": Statistic(population, "geonames", row["population_year"])
        if population is not None
        else None,
        "area_km2": Statistic(area, "geonames") if area is not None else None,
        "neighbours": _split(row["neighbours"]),
        "postal_code_format": row["postal_code_format"],
        "postal_code_regex": row["postal_code_regex"],
    }


def _place(x):
    try:
        return _country(x), None
    except KeyError as not_country:
        try:
            sub = _subregion(x)
        except (KeyError, LookupError):
            raise KeyError(f"no country or subdivision {x!r} ({not_country.args[0]})") from None
        return _country(sub.country), sub


def profile(x, pack=None, store=None):
    """The Profile of a country (any code or name) or a subdivision ("CA-ON", "Karnataka").

    Facts come from the world pack's country_facts layer: `pack` (a pack directory or an opened
    Pack), else the installed world pack via `store` (default: placewise.store.Store()). Missing
    values are None. A subdivision's profile carries only the country-wide facts (currency,
    calling code, conventions ...); its own capital, population and time zones are not sourced.
    """
    c, sub = _place(x)
    facts = _fields(row) if (row := _facts(pack, store).get(c.alpha2)) else {}
    if sub is not None:
        facts = {k: v for k, v in facts.items() if k in _COUNTRY_WIDE}
        return Profile(sub.code, sub.name, sub.kind, c.alpha2, c.alpha3, **facts)
    return Profile(c.alpha2, c.name, "country", c.alpha2, c.alpha3, **facts)
