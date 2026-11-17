"""Country profiles (placewise.world.profile): where their facts live and the values they take."""

PACK = "world"  # the data pack holding the country facts
FACTS_LAYER = "country_facts"  # its layer: one row per country, id "iso:XX"
INSTALL_HINT = "placewise data install world"

# value sets of the profile fields (CLDR's "UK" measurement system is read as imperial-mixed)
MEASUREMENT_SYSTEMS = ("metric", "US", "imperial-mixed")
DRIVING_SIDES = ("left", "right")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
