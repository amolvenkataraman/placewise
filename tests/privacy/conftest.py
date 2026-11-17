"""Shared setup for the privacy tests.

pytest loads this before any test under tests/privacy/ and, in its default (prepend) import mode,
puts this folder on sys.path, so tests in subfolders such as location/ can `import privacy_kit`.
"""
