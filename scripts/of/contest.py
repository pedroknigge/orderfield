"""Field contest: competing plans as sibling fields, selection by contrast.

Haken reading: candidate plans are fast modes; `of contrast` against the
shared SPEC is the field feedback that selects; the winner becomes the
slow order (ACTIVE) and re-enslaves the rest. No debate, no rhetoric —
evidence only (blocking-count ranking plus a minimum floor).

Two verbs (see `of/cli/contend_cmd.py`):
- `of contend` opens N sibling fields from one briefed parent field.
- `of crown` ranks the candidates by contrast and crowns a clear winner.

Not a regime, not `of merge`. Losers are archived with a CONTEST.json
trail (reversible, auditable); nothing is deleted.
"""
from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from of.field import (
    ActiveField,
    PHASES,
    die,
    dump_bytes,
    emit_event,
    field_home,
    field_is_open,
    list_field_homes,
    load_order,
    save_order,
    set_field_home,
    utc_now,
)

CONTEST_KEY = "contest"
CONTEST_TRAIL = "CONTEST.json"
MIN_CANDIDATES = 2
MAX_CANDIDATES = 8


def new_contest_id() -> str:
    return f"ctg_{uuid.uuid4().hex[:8]}"


def _resolve_parent(root: Path, explicit: str | None) -> tuple[str, Path, dict[str, Any]]:
    homes = list_field_homes(root)
    if not homes:
        die("no ORDER. of init --mission '...' --source ... first; contend opens siblings")
    if explicit:
        for fid, home, order in homes:
            if fid == explicit:
                return fid, home, order
        die(f"unknown field {explicit}")
    pointed = ActiveField.read(root)
    if pointed:
        for fid, home, order in homes:
            if fid == pointed:
                return fid, home, order
    if len(homes) == 1:
        return homes[0]
    die(
        "multiple fields; of contend --field <parent-id> "
        "(or of --field <id> contend) to pick the brief holder",
        2,
    )
    raise AssertionError("unreachable")


def open_contest(
    root: Path,
    *,
    mission: str | None,
    source_text: str | None,
    candidates: int,
    phase: str | None = None,
    max_gaps: int,
    parent_id: str | None,
) -> tuple[str, list[str]]:
    """Open N candidate siblings from one briefed parent. Returns (contest, ids)."""
    from of.cli.init_cmd import cmd_new
    from of.spec import load_requirements, read_spec_text

    if not MIN_CANDIDATES <= candidates <= MAX_CANDIDATES:
        die(f"--candidates must be {MIN_CANDIDATES}..{MAX_CANDIDATES}; got {candidates}")
    if max_gaps < 0:
        die(f"--max-gaps must be >= 0; got {max_gaps}")
    parent_fid, parent_home, parent_order = _resolve_parent(root, parent_id)
    set_field_home(parent_home)
    cand_phase = phase or str(parent_order.get("phase") or "explore")
    if cand_phase not in PHASES:
        cand_phase = "explore"
    try:
        text = source_text if source_text is not None else read_spec_text(root)
    except OSError:
        die(f"contend needs a briefed parent field {parent_fid}: of init --source ... first")
    if not str(text or "").strip():
        die(f"contend needs a briefed parent field {parent_fid}: of init --source ... first")
    parent_reqs = load_requirements(root)
    parent_hash = str(parent_reqs.get("spec_hash") or "").strip()
    if not parent_hash:
        die(f"parent field {parent_fid} has no REQUIREMENTS spec_hash; re-ingest its brief")
    contest = new_contest_id()
    ids: list[str] = []
    for cand in range(1, candidates + 1):
        ns = argparse.Namespace(
            mission=mission or str(parent_order.get("mission") or ""),
            phase=cand_phase,
            done_when=None,
            source=text,
            source_file=None,
            origin=None,
            session_id=None,
            parent=None,
        )
        cmd_new(ns)
        order = load_order(root)
        cand_reqs = load_requirements(root)
        if str(cand_reqs.get("spec_hash") or "") != parent_hash:
            die(f"candidate {cand} diverged from the shared brief; aborting contest {contest}")
        # Mother-context inheritance: the parent's pinned plan sources
        # (plan_source + keep-coverage lines) travel into every candidate,
        # or fidelity would see an unpinned field and the plan/docs wealth
        # would be lost at the start — the weakest sum of parts.
        from of.regime import PlanIngress

        inherited = PlanIngress.inherited_pins(parent_order)
        if inherited:
            constraints = [str(item) for item in (order.get("constraints") or [])]
            blob = "\n".join(constraints)
            changed = False
            for line in inherited:
                if line not in blob:
                    constraints.append(line)
                    blob = f"{blob}\n{line}"
                    changed = True
            if changed:
                order["constraints"] = constraints
        order[CONTEST_KEY] = {
            "id": contest,
            "candidate": cand,
            "candidates": candidates,
            "spec_hash": parent_hash,
            "max_gaps": max_gaps,
            "parent": parent_fid,
        }
        save_order(order, root)
        ids.append(str(order["id"]))
    emit_event("contend", contest=contest, parent=parent_fid, candidates=ids, ok=True)
    return contest, ids


def rank(root: Path, contest_id: str) -> tuple[list[dict[str, Any]], str]:
    """Contrast every live candidate. Returns (ranking, shared spec_hash).

    Iterates homes with set_field_home (the multi-home pattern from
    retain): ActiveField.write only moves the ACTIVE pointer for future
    processes, it does not rebind this process. Home binding is restored
    before return. Ranking key: fewer blocking first, RESOLVED gate
    first, more verified_contract first.
    """
    from of.cli.spec_cmd import ContrastReport
    from of.spec import load_requirements

    members = [
        (fid, home, order)
        for fid, home, order in list_field_homes(root)
        if isinstance(order.get(CONTEST_KEY), dict)
        and str(order[CONTEST_KEY].get("id") or "") == contest_id
    ]
    if not members:
        die(f"unknown contest {contest_id}")
    saved = field_home(root)
    entries: list[dict[str, Any]] = []
    spec_hash = ""
    try:
        for fid, home, _order in members:
            set_field_home(home)
            live = load_order(root)
            if not field_is_open(live):
                continue
            reqs = load_requirements(root)
            doc = ContrastReport.document(root, live)
            machine = ContrastReport.machine(doc)
            if not spec_hash:
                spec_hash = str(machine.get("spec_hash") or "")
            elif str(machine.get("spec_hash") or "") != spec_hash:
                die(f"candidate {fid} diverged from the shared brief; contest {contest_id} is void")
            if str(doc.get("gate") or "") == "CLOSE_SKIP":
                continue
            coverage = machine.get("coverage") or {}
            entries.append(
                {
                    "field_id": fid,
                    "gate": str(doc.get("gate") or ""),
                    "ok": bool(doc.get("ok")),
                    "blocking": list(machine.get("blocking") or []),
                    "blocking_n": len(list(machine.get("blocking") or [])),
                    "verified_contract": int(coverage.get("verified_contract") or 0),
                }
            )
    finally:
        set_field_home(saved)
    entries.sort(
        key=lambda e: (
            int(e["blocking_n"]),
            0 if e["gate"] == "RESOLVED" else 1,
            -int(e["verified_contract"]),
            str(e["field_id"]),
        )
    )
    return entries, spec_hash


def decide(
    ranking: list[dict[str, Any]], max_gaps: int
) -> tuple[str, dict[str, Any]]:
    """Return (winner|tie|below_floor, entry). Strict improvement required."""
    if not ranking:
        die("no rankable candidates (all closed or without SPEC)")
    best = ranking[0]
    if int(best["blocking_n"]) > max_gaps:
        return "below_floor", best
    if len(ranking) > 1 and int(ranking[1]["blocking_n"]) <= int(best["blocking_n"]):
        return "tie", best
    return "winner", best


def _archive_live_candidate(
    root: Path, field_id: str, trail: dict[str, Any]
) -> str:
    """Move a live candidate home to the archive with a CONTEST.json trail."""
    from of.retain import ClosedFieldArchive, load_gc_keep, save_gc_keep

    match: tuple[str, Path, dict[str, Any]] | None = None
    for hid, home, order in list_field_homes(root):
        if hid == field_id:
            match = (hid, home, order)
            break
    if match is None:
        die(f"unknown field {field_id}")
    _hid, home, _order = match
    dest = ClosedFieldArchive.dest(root, field_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Direct bytes, not dump_json: under crown's WAL generation a staged
    # write would land in the wrong home (generation keys are home-relative).
    dump_bytes(
        home / CONTEST_TRAIL,
        (json.dumps(trail, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    rel = home.relative_to(root).as_posix()
    dest_rel = dest.relative_to(root).as_posix()
    shutil.move(str(home), str(dest))
    ClosedFieldArchive._release_active(root, field_id)
    keeps = load_gc_keep(root)
    if field_id in keeps:
        keeps.pop(field_id, None)
        save_gc_keep(root, keeps)
    print(f"archived     {rel} -> {dest_rel}  proof={CONTEST_TRAIL}")
    return dest_rel


def crown(
    root: Path,
    contest_id: str,
    *,
    winner_id: str | None = None,
    max_gaps: int | None = None,
    reason: str = "",
    machine_out: bool = False,
) -> dict[str, Any]:
    """Crown the contrast winner. Auto only on strict improvement + floor.

    Ties and below-floor fields print the ranking and exit 2 for a human.
    An explicit --winner is the human path and always records the ranking.
    """
    ranking, spec_hash = rank(root, contest_id)
    floor_gaps = (
        max_gaps
        if max_gaps is not None
        else _contest_floor(root, contest_id)
    )
    auto = winner_id is None
    if winner_id is not None:
        ids = [e["field_id"] for e in ranking]
        if winner_id not in ids:
            die(f"--winner {winner_id} is not a rankable candidate of {contest_id}")
        best = next(e for e in ranking if e["field_id"] == winner_id)
        outcome = "winner-human"
    else:
        outcome, best = decide(ranking, floor_gaps)
        if outcome != "winner":
            _print_ranking(contest_id, ranking, floor_gaps)
            print(f"no crown: {outcome} (human: of crown --contest {contest_id} --winner <id>)")
            raise SystemExit(2)
        outcome = "winner-auto"
    wid = str(best["field_id"])
    losers = [str(e["field_id"]) for e in ranking if str(e["field_id"]) != wid]
    trail = {
        "v": 1,
        "kind": "contest.archive",
        "contest": contest_id,
        "winner": wid,
        "outcome": outcome,
        "reason": reason,
        "crowned_at": utc_now(),
        "ranking": ranking,
    }
    archived: list[str] = []
    for fid in losers:
        archived.append(_archive_live_candidate(root, fid, trail))
    ActiveField.write(root, wid)
    for hid, home, _order in list_field_homes(root):
        if hid == wid:
            set_field_home(home)
            break
    order = load_order(root)
    stamped = dict(order.get(CONTEST_KEY) or {})
    stamped["result"] = {
        "winner": wid,
        "outcome": outcome,
        "reason": reason,
        "crowned_at": str(trail["crowned_at"]),
        "ranking": [
            {
                "field_id": e["field_id"],
                "gate": e["gate"],
                "blocking_n": e["blocking_n"],
                "verified_contract": e["verified_contract"],
            }
            for e in ranking
        ],
        "archived": archived,
    }
    order[CONTEST_KEY] = stamped
    save_order(order, root)
    emit_event(
        "crown",
        contest=contest_id,
        winner=wid,
        outcome=outcome,
        archived=archived,
        ok=True,
    )
    _print_ranking(contest_id, ranking, floor_gaps)
    print(f"crowned      {wid}  ({outcome}; re-enslave: pack/spawn under this ORDER)")
    result = {
        "contest": contest_id,
        "winner": wid,
        "outcome": outcome,
        "spec_hash": spec_hash,
        "ranking": ranking,
        "archived": archived,
    }
    if machine_out:
        print(json.dumps(result, sort_keys=True))
    return result


def _contest_floor(root: Path, contest_id: str) -> int:
    for _fid, _home, order in list_field_homes(root):
        block = order.get(CONTEST_KEY)
        if isinstance(block, dict) and str(block.get("id") or "") == contest_id:
            try:
                return int(block.get("max_gaps", 0))
            except (TypeError, ValueError):
                return 0
    return 0


def _print_ranking(
    contest_id: str, ranking: list[dict[str, Any]], floor_gaps: int
) -> None:
    print(f"contest      {contest_id}  floor max_gaps={floor_gaps}")
    for pos, entry in enumerate(ranking, 1):
        blocking = " ".join(str(b) for b in entry["blocking"]) or "none"
        print(
            f"  #{pos} {entry['field_id']}  gate={entry['gate']}  "
            f"blocking_n={entry['blocking_n']} [{blocking}]  "
            f"verified_contract={entry['verified_contract']}"
        )
