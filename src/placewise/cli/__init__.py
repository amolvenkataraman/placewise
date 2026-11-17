"""The `placewise` command line (`placewise.cli:main`). Exit codes: 0 ok, 1 error, 2 usage.

One module per command group: main (parser and dispatch), data (`placewise data ...`), attribution,
serve (`placewise serve`), server (`placewise server keys ...`); _common holds what they share.
"""

from .main import main

__all__ = ["main"]
