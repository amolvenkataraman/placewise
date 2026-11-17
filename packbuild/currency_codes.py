"""ISO 4217 currency code per country: Unicode CLDR currencyData -> constants/countries/currency_codes.py.

    uv run python -m packbuild.currency_codes            # fetch (once) and regenerate the module
    uv run python -m packbuild.currency_codes --check    # exit 1 if the module is out of date

The only country fact location search needs offline (`placewise.text.currency_for`); every other
fact is in the world pack's country_facts layer (packbuild.country_profiles). The code is the
territory's first current legal tender in CLDR's currencyData, which records the ISO 4217 codes in
use per territory with their dates (the ISO 4217 list itself names several tenders for some
countries without saying which is in use, and carries no open licence).
"""

import argparse
import re
import sys
from pathlib import Path

from .fetch import DEFAULT_CACHE, fetch
from .sources import cldr, url

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "src" / "placewise" / "constants" / "countries" / "currency_codes.py"
_CODE = re.compile(r"[A-Z]{3}")


def source(cache_dir=DEFAULT_CACHE, refresh=False):
    """The cached currencyData.json, downloaded once."""
    link = url("cldr", "currency_data")
    version = re.search(r"/cldr-json/([^/]+)/", link).group(1)
    return fetch(link, Path(cache_dir) / f"cldr-{version}", refresh=refresh)


def cached_path(cache_dir=DEFAULT_CACHE):
    """Where `source` keeps the file (it may not exist yet)."""
    link = url("cldr", "currency_data")
    version = re.search(r"/cldr-json/([^/]+)/", link).group(1)
    return Path(cache_dir) / f"cldr-{version}" / Path(link).name


def codes(path, countries=None):
    """{alpha-2: ISO 4217 code} for the ISO 3166-1 countries CLDR gives a current currency."""
    if countries is None:
        from placewise.constants.countries import BY_ALPHA2

        countries = BY_ALPHA2
    found = cldr.current_currencies(path)
    table = {code: found[code] for code in sorted(countries) if code in found}
    bad = sorted(c for c in table.values() if not _CODE.fullmatch(c))
    if bad:
        raise ValueError(f"not ISO 4217 codes: {bad}")
    return table


def render(table, release):
    """The generated module's text."""
    rows = "\n".join(f'    "{country}": "{currency}",' for country, currency in table.items())
    return f'''"""GENERATED from Unicode CLDR {release} currencyData by packbuild.currency_codes; do not edit.

ISO 4217 code of each country's main current legal tender (CLDR lists the most used first), for
telling which currency amounts for a location are likely in. Countries with no currency of their
own in CLDR (Antarctica) are left out. Other country facts are in the world pack.
Regenerate with `uv run python -m packbuild.currency_codes`.
"""

# fmt: off
# ISO 3166-1 alpha-2 -> ISO 4217
CURRENCY_CODES = {{
{rows}
}}
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the module is out of date")
    parser.add_argument("--refresh", action="store_true", help="download currencyData again")
    args = parser.parse_args(argv)
    path = source(refresh=args.refresh)
    release = re.search(r"/cldr-json/([^/]+)/", url("cldr", "currency_data")).group(1)
    text = render(codes(path), release)
    if args.check:
        current = MODULE.read_text(encoding="utf-8") if MODULE.exists() else ""
        if current != text:
            print(f"{MODULE} is out of date: run python -m packbuild.currency_codes", file=sys.stderr)
            return 1
        return 0
    MODULE.write_text(text, encoding="utf-8")
    print(f"wrote {MODULE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
