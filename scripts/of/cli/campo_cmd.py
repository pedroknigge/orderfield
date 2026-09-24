"""of config / of campo — installed peers and peer election."""
from __future__ import annotations

import argparse

from of.campo import PEERS, Campo
from of.field import field_lock, find_root


def _print_roster(doc: dict) -> None:
    for row in Campo.contestants(doc):
        print(f"{row['id']}  {row['model']}  {row['effort']}")


def cmd_config_show(_args: argparse.Namespace) -> None:
    for line in Campo.audit_lines():
        print(line)
    doc = Campo.read_config()
    rows = Campo.contestants(doc)
    if not rows:
        print("roster      (unset)")
    else:
        _print_roster(doc)
        print(f"config      {Campo.config_path()}")
    print(f"peers       {PEERS}")
    print("next        of config set --contestant MODEL EFFORT")


def cmd_config_set(args: argparse.Namespace) -> None:
    seats = [
        (str(model), str(effort))
        for model, effort in (args.contestant or [])
    ]
    doc = Campo.write_defaults(seats)
    for line in Campo.audit_lines():
        print(line)
    _print_roster(doc)
    print(f"peers       {PEERS}")
    print(f"config      {Campo.config_path()}")


def cmd_campo_settle(_args: argparse.Namespace) -> None:
    root = find_root()
    with field_lock(root, "campo"):
        doc = Campo.settle(root)
    for line in Campo.speak(doc):
        print(line)
    if not doc.get("pinned"):
        raise SystemExit(2)
