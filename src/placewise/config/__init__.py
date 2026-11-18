"""Loading settings: placewise.toml (or .json), the environment and keyword arguments, over the
shipped defaults. See `load_settings`, and the loader module for the full precedence rules.
"""

from .errors import ConfigError
from .loader import config_dir, explain_settings, find_config, load_settings
from .worldview import WorldviewLockedError, effective_worldview
from .write import set_setting, user_config_path

__all__ = [
    "ConfigError",
    "WorldviewLockedError",
    "config_dir",
    "effective_worldview",
    "explain_settings",
    "find_config",
    "load_settings",
    "set_setting",
    "user_config_path",
]
