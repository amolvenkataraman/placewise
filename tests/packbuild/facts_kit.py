"""Fixture files standing in for the country_facts downloads (GeoNames, CLDR, Wikidata): small
excerpts of the real files, with Wikidata's US rows made to disagree so one row is left null."""

from pathlib import Path

DATA = Path(__file__).parent / "data"


def fixture_for(url):
    """The fixture file for a country_facts download URL, or None for other URLs."""
    if "query.wikidata.org" in url:
        return DATA / "wikidata_driving_side.json"
    if url.endswith("/ca-gregorian.json"):
        return DATA / "cldr" / f"dates-{url.split('/')[-2]}.json"
    name = url.rsplit("/", 1)[1]
    if "/cldr-json/" in url:
        return DATA / "cldr" / name
    if name in ("countryInfo.txt", "timeZones.txt"):
        return DATA / name
    return None


def fake_fetch(url, cache_dir, refresh=False):
    path = fixture_for(url)
    if path is None:
        raise AssertionError(f"unexpected download {url}")
    return path
