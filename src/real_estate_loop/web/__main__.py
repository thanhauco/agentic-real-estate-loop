"""Enable ``python -m real_estate_loop.web``."""
from __future__ import annotations

import sys

from .server import run

if __name__ == "__main__":
    sys.exit(run())
