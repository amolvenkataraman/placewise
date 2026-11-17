"""Overrides: file types, the origin tags answers cite, and alias matching."""

FILE_SUFFIXES = (".toml", ".json")  # same structure; TOML preferred where it can be read
SOURCE_PREFIX = "override"  # Result.sources[field] = "override:<origin>", e.g. "override:repo:aliases.toml#1"
ALIAS_NEAR_KM = 50.0  # an alias with `near` applies to searches centred this close to its point
