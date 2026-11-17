"""The settings sections and their typed keys, read off the Settings model."""

import dataclasses
import typing

from placewise.model import Settings

SECTIONS = {f.name: typing.get_type_hints(Settings)[f.name] for f in dataclasses.fields(Settings)}
FIELDS = {name: typing.get_type_hints(cls) for name, cls in SECTIONS.items()}
