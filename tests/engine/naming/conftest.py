import pytest
from naming_kit import write_all


@pytest.fixture(scope="session")
def packs(tmp_path_factory):
    """(world, us, ca, in) pack directories."""
    return write_all(tmp_path_factory.mktemp("naming"))


@pytest.fixture(scope="session")
def geo(packs):
    from placewise.engine import Geocoder

    return Geocoder(packs=list(packs))


@pytest.fixture(scope="session")
def world_only(packs):
    from placewise.engine import Geocoder

    return Geocoder(packs=[packs[0]])
