"""Curated metro and vernacular regions ("GTA", "SF Bay Area", "Delhi NCR"): constants.countries.regions."""

from placewise.constants.countries import METROS

from .countries import country as _country


def regions(country=None):
    """Every curated metro region, or those of one country (any code or name), sorted by name."""
    alpha2 = _country(country).alpha2 if country is not None else None
    return sorted((m for m in METROS if alpha2 is None or m.country == alpha2), key=lambda m: m.name)
