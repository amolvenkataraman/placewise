"""One module per upstream dataset; each turns downloaded files into pack layers (LayerData).

The datasets themselves (attribution, licence, download URLs) are described in the shipped source
registry, src/placewise/sources/<id>.json; loading it is the licence gate, so a denied source or an
unusable licence fails at import, before anything is built.
"""

from placewise.attribution import load_sources

WORLD = ("naturalearth", "geonames", "ourairports")
SOURCES = {id_: source for id_, source in load_sources().items() if id_ in WORLD}
US = ("uscensus",)
SOURCES.update({id_: source for id_, source in load_sources().items() if id_ in US})
IN = ("indiapost-pincode-boundary", "indiapost-pincode-directory")
SOURCES.update({id_: source for id_, source in load_sources().items() if id_ in IN})
CA = ("statcan-boundaries-2021", "statcan-fsa-2021", "statcan-population-2021")
SOURCES.update({id_: source for id_, source in load_sources().items() if id_ in CA})


def url(source_id, name):
    """The registry's download URL `name` for a source; KeyError names both if it's missing."""
    try:
        return SOURCES[source_id].downloads[name]
    except KeyError:
        raise KeyError(f"source {source_id!r} has no download {name!r} in its registry file") from None
