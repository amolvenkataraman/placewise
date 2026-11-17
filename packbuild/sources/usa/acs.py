"""American Community Survey 5-year estimates, table B01003 (total population), from the Census
Bureau's table-based summary file (public domain; registry `uscensus`, download `acs_population`).

One pipe-separated file covers every geography: `GEO_ID|B01003_E001|B01003_M001`, where GEO_ID is
a summary-level prefix ("1600000US" places, incorporated and CDP alike; "860Z200US" ZCTAs;
"0600000US" county subdivisions) followed by the geography's GEOID. Negative estimates are the
summary file's jam codes (no estimate) and are skipped. The keyless summary file needs no API key,
unlike api.census.gov.
"""

import re
from pathlib import Path

PLACE, ZCTA, COUSUB = "1600000US", "860Z200US", "0600000US"
ESTIMATE = "B01003_E001"


def read_population(path, prefixes=(PLACE, ZCTA)):
    """{prefix: {GEOID: estimate}} for the summary levels named by `prefixes`."""
    out = {p: {} for p in prefixes}
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\r\n").split("|")
        if header[:2] != ["GEO_ID", ESTIMATE]:
            raise ValueError(f"{path}: expected GEO_ID|{ESTIMATE}..., got {'|'.join(header[:2])}")
        for line in f:
            geo_id, _, rest = line.partition("|")
            prefix = geo_id[:9]
            if prefix in out:
                value = int(rest.partition("|")[0])
                if value >= 0:
                    out[prefix][geo_id[9:]] = value
    return out


def vintage(path):
    """The estimates' last year, from the file name (acsdt5y2024-b01003.dat: 2020-2024)."""
    m = re.match(r"acsdt5y(\d{4})-", Path(path).name)
    if not m:
        raise ValueError(f"{Path(path).name}: not an ACS 5-year table-based summary file name")
    return int(m.group(1))
