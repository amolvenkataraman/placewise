"""The error every configuration problem raises."""


class ConfigError(ValueError):
    """A configuration value, key or file is wrong; the message says which and where."""
