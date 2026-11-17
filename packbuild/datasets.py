"""Where the curated datasets live: placewise-data's `datasets/` folder, in a checkout beside this
repository (`../placewise-data/datasets`), or wherever $PACKBUILD_DATASETS points.

The datasets (country groups, regions, city aliases ...) are maintained by hand in the data
repository under CC BY 4.0. The package never reads them: packbuild validates them and generates
the offline copies the package ships (constants/countries/groups.py, regions.py, city_aliases.py)
and the packs' curated layers.
"""

import os
from pathlib import Path

ENV_DIR = "PACKBUILD_DATASETS"  # not PLACEWISE_*: placewise's config loader rejects unknown ones
REPO = Path(__file__).resolve().parents[1]


def root():
    """The datasets folder."""
    env = os.environ.get(ENV_DIR)
    return Path(env).expanduser() if env else REPO.parent / "placewise-data" / "datasets"


def path(*parts):
    """A path inside the datasets folder."""
    return root().joinpath(*parts)
