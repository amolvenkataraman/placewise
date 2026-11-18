"""DataSettings.mode and auto_packs: how packs arrive (auto, manual, locked) and which kinds auto
mode may fetch; data.offline stays as the old spelling of locked."""

import pytest

from placewise.model import DataSettings, Settings


def test_default_is_auto_for_country_packs_only():
    data = Settings().data
    assert data.mode == "auto"
    assert data.auto_packs == ("country",)
    assert data.effective_mode == "auto"


def test_offline_is_the_old_spelling_of_locked():
    assert DataSettings(offline=True).effective_mode == "locked"
    assert DataSettings(mode="manual", offline=True).effective_mode == "locked"
    assert DataSettings(mode="locked").effective_mode == "locked"
    assert DataSettings(mode="manual").effective_mode == "manual"
    assert DataSettings(mode="locked").locked and DataSettings(offline=True).locked
    assert not DataSettings(mode="manual").locked


def test_auto_packs_take_kinds_and_normalise_to_a_tuple():
    data = DataSettings.from_dict({"auto_packs": ["country", "parks", "water", "notable", "postal"]})
    assert data.auto_packs == ("country", "parks", "water", "notable", "postal")
    assert DataSettings(auto_packs=[]).auto_packs == ()


@pytest.mark.parametrize("bad", [{"mode": "sometimes"}, {"auto_packs": ["roads"]}, {"auto_packs": ["base"]}])
def test_unknown_modes_and_kinds_are_errors(bad):
    with pytest.raises(ValueError):
        DataSettings.from_dict(bad)
