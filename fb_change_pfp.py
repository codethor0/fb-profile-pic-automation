#!/usr/bin/env python3
"""Backwards-compatible wrapper so the original single-file invocation keeps working:

    python3 fb_change_pfp.py --dir ~/Pictures/pfp --cycle

The real implementation lives in the ``fb_pfp`` package under ``src/``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fb_pfp.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
