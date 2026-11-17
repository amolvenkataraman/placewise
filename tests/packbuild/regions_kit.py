"""Curated regions for the pack build tests, made of the tiny fixtures' units (not the dataset's,
whose members the fixtures don't have)."""

from packbuild import regions


def region(rid, members, country="US", admin1=("CA",), **extra):
    """A dataset entry with the fields the regions layer reads."""
    return {
        "id": rid,
        "short_name": rid.split(":")[1].upper(),
        "name": f"Test region {rid}",
        "country": country,
        "admin1": list(admin1),
        "aliases": [f"{rid} alias"],
        "kind": "metro",
        "members": list(members),
        "definition": {"title": "test", "url": "https://example.org"},
        "notes": "",
        **extra,
    }


# San Francisco and Alameda counties; Clark County alone
US_REGIONS = [
    region("region:test-bay", ["census:06075", "census:06001"]),
    region("region:test-vegas", ["census:32003"], admin1=("NV",)),
]
# Toronto, Peel and Halton census divisions; Milton (a CSD); both parts of the Ottawa - Gatineau CMA
CA_REGIONS = [
    region("region:test-gta", ["statcan:3520", "statcan:3521", "statcan:3524"], "CA", ("ON",)),
    region("region:test-milton", ["statcan:3524009"], "CA", ("ON",)),
    region("region:test-capital", ["statcan:35505", "statcan:24505"], "CA", ("ON", "QC")),
]
# New Delhi's PIN area, by district
IN_REGIONS = [
    region("region:test-delhi", ["pin:110001"], "IN", ("DL",), districts={"DL": ["NEW DELHI"]}),
]


def use_regions(monkeypatch, entries):
    """Make the builders read `entries` instead of datasets/regions."""
    monkeypatch.setattr(regions, "load", lambda dataset=None: [dict(e) for e in entries])
