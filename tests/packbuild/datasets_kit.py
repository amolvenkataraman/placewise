"""Tests that read the real curated datasets (placewise-data/datasets) skip when no checkout is
beside this repository and $PACKBUILD_DATASETS isn't set."""

import pytest

from packbuild import datasets

needs_datasets = pytest.mark.skipif(
    not datasets.root().is_dir(),
    reason=f"curated datasets not found at {datasets.root()} (clone placewise-data beside placewise)",
)
