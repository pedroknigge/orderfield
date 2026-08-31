#!/usr/bin/env python3
"""Orderfield kernel — Haken slaving orchestration. Stdlib only.

Public CLI entry. Internals live in the `scripts/of/` package
(field, spec, pack, regime, cli). Adapters stay in of_adapters.py.
"""
from __future__ import annotations

from of.cli import main


if __name__ == "__main__":
    main()
