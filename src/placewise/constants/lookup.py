"""Point lookup (placewise.engine): how far, how big and how the answer is scored."""

from . import notable, parks, postal, towns, water
from .distance import METRES_PER
from .naming import COUNTRY_PACKS, NAME, STATE

# layers the lookup reads from a pack, by name (docs/pack-format.md, packbuild/README.md)
COUNTRIES = "countries"
ADMIN1 = "admin1"
CITIES = "cities"
AIRPORTS = "airports"
TIMEZONES = "timezones"  # time-zone polygons, in the world pack and country packs (packbuild/timezones.py)
# the zone column of the admin layers (world countries and admin1, US counties, Canadian
# subdivisions; packbuild/timezones.py): "" no entry for the unit (the containing unit's zone
# applies), TZ_NONE an entry with no zone (tzdb records none), else a zone, or zones joined by
# TZ_SEPARATOR for a unit split along a line no pack draws (the first is the default)
TZ_FIELD = "tz"
TZ_NONE = "-"
TZ_SEPARATOR = "|"
DEFAULT_PACK = "world"  # what Geocoder() opens through the store when no packs are given
# the packs a store-backed Geocoder opens beside it when installed, in this order; auto mode fetches
# only these (a pack this placewise doesn't read is never downloaded for it)
OPTIONAL_PACKS = (*COUNTRY_PACKS, postal.PACK, water.PACK, *parks.PACKS, notable.PACK, towns.PACK)

# rule names in Result.sources ("world/countries:offshore")
POLYGON = "polygon"  # the point is inside the feature
OFFSHORE = "offshore"  # outside every feature of the layer, within TERRITORIAL_KM of this one
NEAREST = "nearest"  # inside the country, outside its admin1 polygons (sliver between the layers)
SCORE = "score"  # the provisional city score below
SPLIT = "split"  # a time-zone unit split along a line no pack draws: its nearest town's zone decided
WORLDVIEW = "worldview"  # the zone of the country the worldview reports, not the administering one's
# Result.matches (placewise.engine._results.matches): the rules that put the point inside the field's place;
# OFFSHORE is "offshore", every other rule a fallback ("near")
MATCH_WITHIN_RULES = frozenset({POLYGON, WORLDVIEW, STATE, NAME})

# 12 nautical miles, the territorial sea (UNCLOS art. 3). Natural Earth's 1:10m coastline misses
# some coastal points (piers, harbours, whole city centres like Sevastopol's) by hundreds of
# metres, so a point this close to a country is still reported in it.
TERRITORIAL_KM = 12 * METRES_PER["nmi"] / 1000
# Borders (placewise.engine._borders): a country pack's state or province corrects Natural Earth's
# country only for points at least this far inside it; closer, the point is within the unit's own
# generalisation (Census and StatCan cartographic boundaries are drawn to tens of metres), and
# Natural Earth's answer stands (the brink of the Horseshoe Falls, 23 m inside New York's outline)
BORDER_DEPTH_KM = 0.05
# the id prefix of places named by an ISO code ("iso:US-NY"): the world pack's admin1 ids
ISO_ID_PREFIX = "iso:"

# 200 nautical miles, the exclusive economic zone: how far out `water` still names the nearest
# country. Beyond it a point is just "Offshore".
WATER_SEARCH_KM = 200 * METRES_PER["nmi"] / 1000

# Provisional city rule (replaced by municipal polygons in the naming phase): among GeoNames
# cities within CITY_RADIUS_KM, pick the highest population**ALPHA / (km + D0).
CITY_RADIUS_KM = 30.0  # farther than this a place isn't "in" a city any more, even a huge one
CITY_SCORE_ALPHA = 0.3  # 0.3: a 1,000x bigger city wins from ~8x farther; 0.5 let metros swallow suburbs
CITY_SCORE_D0_KM = 2.0  # softens distance near a city's point, which is a centre, not the whole town
CITY_MIN_POPULATION = 1_000  # cities1000 has rows with population 0; count them as its threshold
CITY_OTHER_ADMIN1_FACTOR = 0.5  # a city in another state/province must score twice as well to win
CITY_CANDIDATES = 16  # nearest cities scored per point (plus the notable ones below)
# GeoNames feature codes that are not towns of their own: sections of a city (PPLX, e.g. Toronto's
# neighbourhoods), historical, abandoned or destroyed places, and historical capitals
CITY_EXCLUDED_FEATURE_CODES = frozenset({"PPLX", "PPLH", "PPLQ", "PPLW", "PPLCH"})

# "notable" cities: listed in Result.near, and always scored for the city even when dozens of
# small places are nearer
NOTABLE_POPULATION = 50_000
NOTABLE_CANDIDATES = 8  # per point; MAX_NEAR (5) plus the chosen city plus slack

# an airport's point is near its centre and a big airport is a few km across: within this the
# point is AT the airport, otherwise NEAR it (up to NearSettings.airport)
AIRPORT_AT_KM = 2.0

# where no timezones polygon answers, the nearest city of the same country gives the time zone; and in
# a split time-zone unit the nearest city inside it decides between its zones. Both search this
# far, which covers the emptiest inhabited land
TZ_SEARCH_KM = 3_000.0
# cell size (degrees) of the per-country city grids that search runs on. Only points with no
# same-country city within CITY_RADIUS_KM get there, so they are far from towns: coarse cells
# reach the answer in a few steps where density-sized cells (fine, for city clusters) take dozens
TZ_FALLBACK_CELL_DEG = 2.0

# far offshore, the label names the best city within this ("Offshore, 15 km S of Toronto")
OFFSHORE_LABEL_KM = 100.0
OFFSHORE_LABEL = "Offshore"
COMPASS_POINTS = 8  # "NE", not "ENE": labels are for people

# worldviews: Natural Earth's per-view columns (packbuild/sources/naturalearth.py)
VIEW_COLUMN = "adm0_a3_{view}"  # the admin-0 unit a view groups each polygon into
NO_VIEW = "-99"  # Natural Earth's "no value" (the un and wb columns hold nothing else)
DE_FACTO = "de_facto"  # the default polygons: who administers the ground
DISPUTED = "disputed"  # in an order: report no country where the views disagree
