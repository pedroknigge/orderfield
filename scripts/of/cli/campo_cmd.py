"""of config / of campo — installed peers and peer election."""
from __future__ import annotations

import argparse

from of.campo import DEADLINE_ENV, DEFAULT_DEADLINE_S, PEERS, Campo
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
    stored = doc.get("deadline_s")
    ceiling = float(stored) if stored is not None else DEFAULT_DEADLINE_S
    source = "config" if stored is not None else "code default"
    print(
        f"deadline_s  {ceiling:g}s max "
        f"({source}; {DEADLINE_ENV} overrides)"
    )
    print(f"peers       {PEERS}")
    print(config_next_line(len(rows)))


def config_next_line(seats: int) -> str:
    """Leader-directed next for `of config`. Stored roster = Campo default."""
    if seats >= 2:
        return (
            f"next        Campo is default: of new enters Campo with this "
            f"roster ({seats} seats). Leader offers it as the default answer "
            f"to \"which models compete in Campo?\"; of config set only if "
            f"the user changes it"
        )
    return (
        "next        leader: ask the user which models compete in Campo "
        "(of config audit); then of config set --contestant MODEL EFFORT; "
        "then of new --campo"
    )


def cmd_config_set(args: argparse.Namespace) -> None:
    seats = [
        (str(model), str(effort))
        for model, effort in (args.contestant or [])
    ]
    deadline = getattr(args, "deadline", None)
    doc = Campo.write_config(
        seats=seats or None,
        deadline_s=None if deadline is None else float(deadline),
    )
    for line in Campo.audit_lines():
        print(line)
    if Campo.contestants(doc):
        _print_roster(doc)
    stored = doc.get("deadline_s")
    if stored is not None:
        print(f"deadline_s  {float(stored):g}s max")
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
