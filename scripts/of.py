#!/usr/bin/env python3
"""Orderfield kernel — Haken slaving orchestration. Stdlib only.

Public CLI entry. Internals live in the `scripts/of/` package
(field, spec, pack, regime, cli package). Adapters stay in of_adapters.py.
"""
from __future__ import annotations

import sys

# Compatibility floor (SKILL.md `compatibility:`). Checked before any package
# import so an old interpreter gets one line, not a SyntaxError traceback.
PYTHON_FLOOR = (3, 11)

if sys.version_info[:2] < PYTHON_FLOOR:
    sys.stderr.write(
        "of: error: python: Orderfield requires Python %d.%d+ (found %d.%d)\n"
        % (PYTHON_FLOOR + tuple(sys.version_info[:2]))
    )
    sys.exit(1)

from of.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
