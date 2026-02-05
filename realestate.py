#!/usr/bin/env python
"""Zero-install launcher: `python realestate.py` from the repo root.

Adds ``src`` to the path so the package imports without `pip install`.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from real_estate_loop.cli import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run())
