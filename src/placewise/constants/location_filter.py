"""The settings a location filter takes (see placewise.text.LocationFilter)."""

# how remote locations are judged: every one, ones limited to an allowed country or not limited at
# all, only ones that state an allowed limit, or none (remote passes only through an office place)
REMOTE_POLICIES = ("any", "scoped", "strict", "deny")
# what to do with a location in which no country can be found
UNKNOWN_POLICIES = ("keep", "drop")
