"""One module per upstream dataset; each turns downloaded files into pack layers (LayerData).

The datasets themselves (attribution, licence, download URLs) are described in the shipped source
registry, src/placewise/sources/<purpose>.json (one file per purpose, listing sources per region);
loading it is the licence gate, so a denied source or an unusable licence fails at import, before
anything is built.
"""

from placewise.attribution import load_sources

SOURCES = load_sources()


def url(source_id, name):
    """The registry's download URL `name` for a source; KeyError names both if it's missing."""
    try:
        return SOURCES[source_id].downloads[name]
    except KeyError:
        raise KeyError(f"source {source_id!r} has no download {name!r} in its registry file") from None
