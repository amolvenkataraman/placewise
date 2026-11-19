"""Town and city outlines world-wide: the optional world-towns pack (packbuild.towns,
placewise.engine.naming.towns)."""

# the pack and its one polygon layer; the default Geocoder opens the pack when it is installed
PACK = "world-towns"
LAYER = "towns"
# the layer's `class` values: a GHS-SMOD urban centre (50,000+ people at 1,500/km²) or a town
# (a dense or semi-dense urban cluster, 5,000+ people)
CENTRE = "centre"
TOWN = "town"
# what pack.json says the pack covers: every country, except those whose own packs name places
# (the outlines leave them out, and the lookup never uses one there)
COVERS = ("*",)
LEFT_OUT = ("US", "CA", "IN")
