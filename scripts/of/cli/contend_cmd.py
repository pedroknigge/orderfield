"""of contend / of crown — plan contest between sibling fields.

Contend opens N candidate fields from one briefed parent. Crown ranks the
candidates with of-contrast evidence and crowns a clear winner as the slow
order. Ties and below-floor fields exit 2 for a human. Losers are archived
with a CONTEST.json trail, never deleted. Not a regime, not of merge.
"""
from __future__ import annotations

import argparse
import json
from contextlib import nullcontext, redirect_stdout

from of.contest import crown, open_contest
from of.field import die, find_root, refuse_child_forge


def cmd_contend(args: argparse.Namespace) -> None:
    refuse_child_forge("of contend")
    root = find_root()
    machine = bool(getattr(args, "json_out", False))
    # Candidate creation also prints the human-readable 'of new' report.
    with redirect_stdout(None) if machine else nullcontext():
        contest_id, ids = open_contest(
            root,
            mission=getattr(args, "mission", None),
            source_text=getattr(args, "source", None),
            candidates=int(getattr(args, "candidates", 3)),
            phase=getattr(args, "phase", None),
            max_gaps=int(getattr(args, "max_gaps", 0)),
            parent_id=getattr(args, "field_id", None),
        )
    if machine:
        print(json.dumps({"contest": contest_id, "candidates": ids}, sort_keys=True))
        return
    print(f"contest      {contest_id}")
    for pos, fid in enumerate(ids, 1):
        print(f"  candidate #{pos} {fid}")
    print(
        "next: run each plan in its field "
        "(of --field <id> pack/spawn/collect), then "
        f"of crown --contest {contest_id}"
    )


def cmd_crown(args: argparse.Namespace) -> None:
    refuse_child_forge("of crown")
    root = find_root()
    if getattr(args, "field_id", None):
        die("of crown ignores --field; pick a winner with --winner <id>")
    contest_id = str(getattr(args, "contest", None) or "").strip()
    if not contest_id:
        die("of crown --contest is required")
    winner = getattr(args, "winner", None)
    winner_id = str(winner).strip() if winner else None
    raw_gaps = getattr(args, "max_gaps", None)
    crown(
        root,
        contest_id,
        winner_id=winner_id,
        max_gaps=None if raw_gaps is None else int(raw_gaps),
        reason=str(getattr(args, "reason", None) or ""),
        machine_out=bool(getattr(args, "json_out", False)),
    )
