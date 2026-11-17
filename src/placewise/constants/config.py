"""Where configuration comes from: file names, environment variables and their spellings."""

from . import server, store

CONFIG_FILENAMES = ("placewise.toml", "placewise.json")  # TOML first; JSON for 3.10 without tomli
APP_DIR_NAME = store.APP_DIR_NAME

ENV_PREFIX = "PLACEWISE_"  # PLACEWISE_<SECTION>_<KEY>, e.g. PLACEWISE_NEAR_AIRPORT=5
ENV_CONFIG = "PLACEWISE_CONFIG"  # path to the config file
# placewise variables that aren't settings, so the PLACEWISE_<SECTION>_<KEY> check skips them
ENV_E2E_PACKS = "PLACEWISE_E2E_PACKS"  # where the end-to-end tests find built packs (tests/e2e)
ENV_RESERVED = frozenset({ENV_CONFIG, server.ENV_KEYS_FILE, ENV_E2E_PACKS})
# older or shorter spellings, read as the setting they name (the full spelling wins if both are set)
ENV_ALIASES = {
    store.ENV_DATA_DIR: ("data", "data_dir"),
    store.ENV_INDEX_URL: ("data", "index_url"),
}

TRUE_WORDS = frozenset({"1", "true", "yes", "on"})
FALSE_WORDS = frozenset({"0", "false", "no", "off"})
LIST_SEPARATOR = ","  # tuple settings in env: PLACEWISE_WORLDVIEW_ORDER=IN,de_facto
