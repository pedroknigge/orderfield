"""of config / of campo — contestant defaults and peer election."""
from __future__ import annotations

import argparse

from of.campo import Campo
from of.field import field_lock, find_root


def _print_roster(doc: dict) -> None:
    for row in Campo.contestants(doc):
        print(
            f"{row['id']}  {row['harness']}  {row['model']}  {row['effort']}"
        )


def cmd_config_show(_args: argparse.Namespace) -> None:
    doc = Campo.read_config()
    if not Campo.contestants(doc):
        print("contestants  (unset)")
        print(f"example  {Campo.example_set_line()}")
        return
    _print_roster(doc)
    print(f"config  {Campo.config_path()}")


def cmd_config_set(args: argparse.Namespace) -> None:
    seats = [
        (str(harness), str(model), str(effort))
        for harness, model, effort in (args.contestant or [])
    ]
    doc = Campo.write_defaults(seats)
    _print_roster(doc)
    print(f"config  {Campo.config_path()}")


def cmd_campo_settle(_args: argparse.Namespace) -> None:
    root = find_root()
    with field_lock(root, "campo"):
        doc = Campo.settle(root)
    for line in Campo.speak(doc):
        print(line)
    if not doc.get("pinned"):
        raise SystemExit(2)
