"""of config / of campo — contestant defaults and peer election."""
from __future__ import annotations

import argparse

from of.campo import Campo
from of.field import field_lock, find_root


def cmd_config_show(_args: argparse.Namespace) -> None:
    doc = Campo.read_config()
    models = list(doc.get("models") or [])
    if not models:
        print(f"effort  {doc.get('effort')}")
        print("models  (unset)")
        print("next    of config set --model A --model B --effort medium")
        return
    ids = " ".join(row["id"] for row in Campo.contestants(doc))
    print(f"effort  {doc.get('effort')}")
    print("models  " + " ".join(str(item) for item in models))
    print(f"ids     {ids}")


def cmd_config_set(args: argparse.Namespace) -> None:
    models = [str(item) for item in (args.model or []) if str(item).strip()]
    doc = Campo.write_defaults(models, getattr(args, "effort", None))
    ids = " ".join(row["id"] for row in Campo.contestants(doc))
    print(f"effort  {doc['effort']}")
    print("models  " + " ".join(doc["models"]))
    print(f"ids     {ids}")
    print(f"config  {Campo.config_path()}")


def cmd_campo_settle(_args: argparse.Namespace) -> None:
    root = find_root()
    with field_lock(root, "campo"):
        doc = Campo.settle(root)
    for line in Campo.speak(doc):
        print(line)
    if not doc.get("pinned"):
        raise SystemExit(2)
