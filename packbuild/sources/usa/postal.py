"""ZIP Code postal city names for the US pack's ZCTAs: the name USPS gives a ZIP Code's addresses
(89109 -> Las Vegas, though the Strip is in Paradise CDP; 94128 -> San Francisco for SFO).

USPS sells its City State file under a licence that forbids copying, so the names come from:

- ZIP Code Business Patterns totals (`uscensus`, download `zip_cities`, public domain): the USPS
  city name of every ZIP Code with a business establishment (about 31,000 of the 33,791 ZCTAs),
  upper case, punctuation dropped ("WINSTON SALEM");
- GeoNames US postal codes (`geonames`, download `postal_us`, CC BY 4.0) for the ZIP Codes
  Business Patterns lacks (mostly rural residential ones). Where both have a ZIP Code they agree on
  99.9% of names once spelling is ignored; Business Patterns is newer (92509 Jurupa Valley,
  incorporated 2011, where GeoNames still says Riverside), so it goes first;
- the 2020 ZCTA-to-place relationship file (`uscensus`, download `zcta_place`, public domain),
  which says which census places overlap each ZCTA: it picks the place a postal name means when a
  state has two of that name. A postal city that overlaps none (SFO's San Francisco) is still
  matched by name within the state.

A matched postal city is shown with its census place's spelling ("MC LEAN" -> McLean), otherwise
with GeoNames' when it agrees, else in title case.
"""

import csv
import re
import unicodedata

ZBP, GEONAMES = "zbp", "geonames"
# words USPS and the Census spell differently: "Saint Louis" / "St. Louis", "Mount" / "Mt."
_ABBREVIATIONS = {"saint": "st", "sainte": "ste", "mount": "mt", "fort": "ft"}


def read_zbp(path):
    """{ZIP: (city, state)} from a ZIP Code Business Patterns totals file (zbp23totals.txt)."""
    with open(path, encoding="utf-8", newline="") as f:
        return {
            row["zip"]: (row["city"].strip(), row["stabbr"].strip())
            for row in csv.DictReader(f)
            if row["city"].strip()
        }


def read_geonames_postal(path):
    """{ZIP: (place name, state code)} from GeoNames' US.txt (tab-separated, UTF-8)."""
    out = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) > 4 and row[2].strip():
                out.setdefault(row[1].strip(), (row[2].strip(), row[4].strip()))
    return out


def read_zcta_places(path):
    """{ZCTA: [place GEOID, ...]} from the ZCTA-to-place relationship file, in file order."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="|"):
            zcta, place = row["GEOID_ZCTA5_20"], row["GEOID_PLACE_20"]
            if zcta and place:
                out.setdefault(zcta, []).append(place)
    return out


def name_key(name):
    """A name for matching postal and census spellings: accents, case, spacing and punctuation
    ignored, and Saint/Mount/Fort read as St/Mt/Ft."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    words = re.findall(r"[a-z0-9]+", plain)
    return "".join(_ABBREVIATIONS.get(w, w) for w in words)


def title_case(name):
    return " ".join(w.capitalize() for w in name.split())


def postal_cities(zctas, zbp, geonames, places, overlaps):
    """{ZCTA: {"city", "place", "source"}} for each ZCTA: the postal city name, the GEOID of the
    census place it names ("" if none) and where the name came from ("zbp", "geonames" or "").
    `places` is rows of (GEOID, name, state, incorporated, population); `overlaps` is
    read_zcta_places' result."""
    by_name = {}
    for geoid, name, state, incorporated, population in places:
        by_name.setdefault((state, name_key(name)), []).append((geoid, name, incorporated, population or 0))
    out = {}
    for zcta in zctas:
        if zcta in zbp:
            (raw, state), source = zbp[zcta], ZBP
        elif zcta in geonames:
            (raw, state), source = geonames[zcta], GEONAMES
        else:
            out[zcta] = {"city": "", "place": "", "source": ""}
            continue
        key = name_key(raw)
        here = set(overlaps.get(zcta, ()))
        candidates = by_name.get((state, key), [])
        best = min(candidates, key=lambda c: (c[0] not in here, not c[2], -c[3], c[0]), default=None)
        if best is not None:
            city = best[1]
        elif zcta in geonames and name_key(geonames[zcta][0]) == key:
            city = geonames[zcta][0]
        else:
            city = title_case(raw)
        out[zcta] = {"city": city, "place": best[0] if best else "", "source": source}
    return out
