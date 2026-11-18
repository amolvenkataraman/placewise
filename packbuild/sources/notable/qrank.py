"""QRank (CC0): page views over the past 52 weeks per Wikidata item, summed across Wikimedia
projects (qrank.toolforge.org).

The registry's `qrank` download is one dated file (`qrank-YYYYMMDD.csv.gz`, `Entity,QRank`,
items without views left out); its version and SHA-256 are pinned there and the cache sidecar
records them. QRank keeps only its three newest files, so a build that must be repeated reads the
cached copy (packbuild.fetch never downloads a cached file again unless asked to).
"""

import gzip
from pathlib import Path

from ...fetch import fetch as fetch_file
from .. import url

SOURCE = "qrank"


def fetch(cache_dir, refresh=False):
    return fetch_file(url(SOURCE, "qrank"), Path(cache_dir) / "qrank", refresh=refresh, timeout=900)


def pageviews(path, qids):
    """{qid: page views} for the wanted items (absent: no views)."""
    wanted = {q.encode() for q in qids}
    found = {}
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as f:
        header = f.readline().strip()
        if header != b"Entity,QRank":
            raise ValueError(f"{path}: header {header!r}, expected b'Entity,QRank'")
        for line in f:
            qid, _, views = line.partition(b",")
            if qid in wanted:
                found[qid.decode()] = int(views)
    return found
