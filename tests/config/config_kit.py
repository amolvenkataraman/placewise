"""Shared helpers for the config tests."""

import json


def write_json(path, doc):
    path.write_text(json.dumps(doc))
    return path
