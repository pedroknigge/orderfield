"""SPEC commands: spec, spec-diff, contrast, close, eval fixtures."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from of.field import (
    FIELD_SPEC_MD,
    PULSE_STALE_MINUTES,
    FieldSignal,
    PackedAge,
    die,
    dump_json,
    emit_event,
    field_generation,
    field_home,
    field_is_file,
    field_read_text,
    field_lock,
    find_root,
    kernel_repo_root,
    load_json,
    load_order,
    require_public_schema,
    save_order,
    session_path,
    sha256_text,
    snapshot_session,
    spec_path,
    utc_now,
    wave_dir,
)
from of.regime import DoneWhenLint, done_when_closed, mark_done_when_closed
from of.pack import PACKET_IDENTITY_FIELDS, packet_digest, truncate_slice
from of.spec import (
    append_amendment,
    append_binding_line,
    contrast_rows,
    decorate_requirement,
    discard_disposable_ingest,
    extract_requirements_from_spec,
    find_requirement,
    load_requirements,
    load_user_json,
    merge_extracted_requirements,
    read_brief_file,
    read_spec_text,
    require_req_id,
    require_spec_intact,
    requirement_close_ok,
    requirement_counts,
    requirement_coverage_errors,
    requirement_is_pair,
    requirement_source_cite,
    requirement_surface,
    save_requirements,
    snapshot_spec,
    spec_diff_lines,
    spec_id_line_span,
    spec_mentions_req_id,
    sync_order_spec_fields,
    warn_if_deictic_brief,
    write_spec,
)



def cmd_spec(args: argparse.Namespace) -> None:
    """Binding-requirements ledger. Kernel does not LLM-extract; --extract is heuristic."""
    root = find_root()
    # LOCK-002: SPEC.md, REQUIREMENTS and ORDER are the authority ledger.
    # `spec` is in MUTATING_COMMANDS, so the CLI path already holds the lock;
    # this nested (re-entrant, no-op) acquisition guards direct callers/tests.
    if not (root / ".orderfield").is_dir():
        load_order(root)  # dies "no ORDER" without creating a stray field.lock
    with field_lock(root, "spec"):
        _cmd_spec_locked(args, root)


def _cmd_spec_locked(args: argparse.Namespace, root: Path) -> None:
    order = load_order(root)
    data = load_requirements(root)
    changed = False
    # ORDER deltas produced by this command; applied to a fresh ORDER read
    # right before the revision bump, never to the copy loaded above.
    spec_updates: dict[str, Any] = {}
    amend_file = getattr(args, "amend_file", None)
    amend_text = getattr(args, "amend", None)
    revise_file = getattr(args, "revise_file", None)
    revise_text = getattr(args, "revise", None)
    modes = [bool(amend_file), bool(amend_text), bool(revise_file), bool(revise_text)]
    if sum(modes) > 1:
        die("pass only one of --amend / --amend-file / --revise / --revise-file")
    ledger_edits = [
        flag
        for flag, present in (
            ("--from-file", getattr(args, "from_file", None)),
            ("--extract", getattr(args, "extract", False)),
            ("--add", getattr(args, "add", None)),
            ("--supersede", getattr(args, "supersede", None)),
        )
        if present
    ]
    if sum(modes) == 1 and ledger_edits:
        # SPEC.md is written first; a later ledger failure would leave ORDER
        # behind the spec hash. Two commands keep SPEC and ORDER moving together.
        die(
            "--amend/--revise cannot be combined with "
            + "/".join(ledger_edits)
            + "; amend or revise first, then edit requirements in a second command"
        )
    ingest_source: Path | None = None
    if amend_file or amend_text:
        if amend_file:
            incoming = read_brief_file(str(amend_file), flag="--amend-file")
            warn_if_deictic_brief(incoming, flag="--amend-file")
            if str(amend_file) != "-":
                ingest_source = Path(amend_file)
        else:
            incoming = str(amend_text)
            warn_if_deictic_brief(incoming, flag="--amend")
        creating = not spec_path(root).is_file()
        if creating:
            new_hash = write_spec(root, incoming, revise=True)
            extracted = extract_requirements_from_spec(incoming)
            merge_extracted_requirements(data, extracted)
            print(f"spec created {FIELD_SPEC_MD}  hash={new_hash[:12]}…")
            print(f"requirements {len(extracted)} extracted from original brief")
        else:
            require_spec_intact(root, order)
            snap = snapshot_spec(root)
            current = read_spec_text(root)
            merged = append_amendment(current, incoming)
            new_hash = write_spec(root, merged, revise=True)
            extracted = extract_requirements_from_spec(
                incoming, existing=data.get("requirements") or []
            )
            added = merge_extracted_requirements(data, extracted)
            if snap:
                print(f"spec-log    {snap.relative_to(root)}")
            print(f"spec amended {new_hash[:12]}…")
            if added:
                print(
                    f"requirements +{len(extracted)} from amendment "
                    "(IDs continue; original still binding)"
                )
        data["spec_hash"] = new_hash
        spec_updates.update(
            {"spec_ref": FIELD_SPEC_MD, "spec_hash": new_hash, "spec_closed": False}
        )
        changed = True
    elif revise_file or revise_text:
        creating = not spec_path(root).is_file()
        old_hash = str(order.get("spec_hash") or "")
        if not creating:
            old_hash = old_hash or sha256_text(read_spec_text(root))
            snap = snapshot_spec(root)
            if snap:
                print(f"spec-log    {snap.relative_to(root)}")
        if revise_file:
            source_text = read_brief_file(str(revise_file), flag="--revise-file")
            warn_if_deictic_brief(source_text, flag="--revise-file")
            if str(revise_file) != "-":
                ingest_source = Path(revise_file)
        else:
            source_text = str(revise_text)
            warn_if_deictic_brief(source_text, flag="--revise")
        new_hash = write_spec(root, source_text, revise=True)
        data["spec_hash"] = new_hash
        spec_updates.update(
            {"spec_ref": FIELD_SPEC_MD, "spec_hash": new_hash, "spec_closed": False}
        )
        changed = True
        if creating:
            print(f"spec created {FIELD_SPEC_MD}  hash={new_hash[:12]}…")
        else:
            print(f"spec revised {old_hash[:12]}… -> {new_hash[:12]}…")
            print(
                "existing requirement IDs stay until of spec --supersede ID; "
                "of spec --extract for new ones"
            )
    else:
        require_spec_intact(root, order)
    if getattr(args, "extract", False):
        spec = spec_path(root)
        if not spec.is_file():
            die("no SPEC.md; of init --source or of spec --amend")
        text = read_spec_text(root)
        extracted = extract_requirements_from_spec(
            text, existing=data.get("requirements") or []
        )
        if merge_extracted_requirements(data, extracted):
            changed = True
        data["spec_hash"] = sha256_text(text)
    if getattr(args, "from_file", None):
        path = Path(args.from_file)
        if not path.is_file():
            die(f"--from-file not found: {args.from_file}")
        incoming = load_user_json(path, flag="--from-file")
        items = incoming if isinstance(incoming, list) else incoming.get("requirements")
        if not isinstance(items, list):
            die("--from-file must be a list or {requirements: [...]}")
        for raw in items:
            if not isinstance(raw, dict):
                die("requirement entries must be objects")
            rid = require_req_id(str(raw.get("id") or ""))
            text = str(raw.get("text") or "").strip()
            if not text:
                die(f"requirement {rid} missing text")
            item = find_requirement(data, rid)
            if item is None:
                incoming_item = decorate_requirement(
                    {
                        "id": rid,
                        "text": text,
                        "binding": bool(raw.get("binding", True)),
                        "owned_by": list(raw.get("owned_by") or []),
                        "status": str(raw.get("status") or "unowned"),
                        "origin": str(raw.get("origin") or "from-file"),
                    }
                )
                if raw.get("surface") in {"contract", "internal"}:
                    incoming_item["surface"] = raw["surface"]
                if "pair" in raw:
                    incoming_item["pair"] = bool(raw["pair"])
                data.setdefault("requirements", []).append(incoming_item)
            else:
                item["text"] = text
                if "binding" in raw:
                    item["binding"] = bool(raw["binding"])
            changed = True
    add_id = getattr(args, "add", None)
    add_text = getattr(args, "text", None)
    if add_id or add_text:
        if not add_id or not add_text:
            die("of spec --add ID requires --text")
        rid = require_req_id(add_id)
        if find_requirement(data, rid) is not None:
            die(f"requirement {rid} already exists")
        added_text = str(add_text).strip()
        added = decorate_requirement(
            {
                "id": rid,
                "text": added_text,
                "binding": not bool(getattr(args, "non_binding", False)),
                "owned_by": [],
                "status": "unowned",
                "origin": "added",
            }
        )
        surface_arg = str(getattr(args, "surface", None) or "").strip().lower()
        if surface_arg in {"contract", "internal"}:
            added["surface"] = surface_arg
        spec_file = spec_path(root)
        current_spec = read_spec_text(root) if spec_file.is_file() else ""
        if not spec_mentions_req_id(current_spec, rid):
            merged = append_binding_line(current_spec, rid, added_text)
            new_hash = write_spec(root, merged, revise=True)
            spec_updates.update(
                {
                    "spec_ref": FIELD_SPEC_MD,
                    "spec_hash": new_hash,
                    "spec_closed": False,
                }
            )
            span = spec_id_line_span(merged, rid)
            if span:
                added["source"] = {
                    "spec_line_start": span[0],
                    "spec_line_end": span[1],
                }
            print(f"spec        bound {rid} in {FIELD_SPEC_MD}")
        data.setdefault("requirements", []).append(added)
        changed = True
    both_sides = bool(getattr(args, "both_sides", False))
    for rid in getattr(args, "verified_internal", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "verified_internal"
        changed = True
        if requirement_surface(item) == "contract":
            print(
                f"of: note — {rid} has a public surface; "
                "of spec --verified-contract after exercising the CLI/API "
                "(unit tests are VERIFIED_INTERNAL, not close).",
                file=sys.stderr,
            )
    for rid in getattr(args, "verified", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "verified_internal"
        changed = True
        if requirement_surface(item) == "contract":
            print(
                f"of: note — {rid} has a public surface; "
                "of spec --verified-contract after exercising the CLI/API "
                "(unit tests are VERIFIED_INTERNAL, not close).",
                file=sys.stderr,
            )
    for rid in getattr(args, "verified_contract", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        if requirement_is_pair(item) and not both_sides:
            die(
                f"{rid} is pair-shaped (same/different, success/fail, …); "
                "exercise both sides at the public surface, then "
                f"of spec --verified-contract {rid} --both-sides"
            )
        item["status"] = "verified_contract"
        if both_sides:
            item["pair_checked"] = True
        changed = True
    for rid in getattr(args, "failed", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "failed"
        changed = True
    for rid in getattr(args, "supersede", None) or []:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        item["status"] = "superseded"
        changed = True
        print(f"superseded  {rid}")
    if changed:
        spec = spec_path(root)
        if spec.is_file():
            data["spec_hash"] = sha256_text(read_spec_text(root))
        # REQUIREMENTS then ORDER in one field generation (WAL-001). A crash
        # before publish leaves the previous generation readable.
        save_requirements(data, root)
        identity = bool(
            getattr(args, "extract", False)
            or getattr(args, "from_file", None)
            or getattr(args, "add", None)
            or getattr(args, "revise_file", None)
            or getattr(args, "revise", None)
            or getattr(args, "amend_file", None)
            or getattr(args, "amend", None)
            or getattr(args, "supersede", None)
        )
        if identity:
            # LOCK-002: re-read ORDER under the lock right before mutating
            # revision/spec_hash; carry only this command's spec deltas.
            order = load_order(root)
            order.update(spec_updates)
            sync_order_spec_fields(order, root)
            order["rev"] = int(order["rev"]) + 1
            save_order(order, root)
            print(f"rev={order['rev']}")
        snapshot_session(root, "spec")
        discard_disposable_ingest(root, ingest_source)
    counts = requirement_counts(data)
    print(
        f"requirements  {counts['total']} total  "
        f"owned {counts['owned']}  verified {counts['verified']}  "
        f"contract {counts['verified_contract']}  internal {counts['verified_internal']}  "
        f"failed {counts['failed']}  unowned {counts['unowned']}  "
        f"unverified {counts['unverified']}  superseded {counts['superseded']}"
    )
    for item in data.get("requirements") or []:
        owners = ",".join(item.get("owned_by") or []) or "-"
        bind = "binding" if item.get("binding", True) else "advisory"
        surf = requirement_surface(item)
        pair = "pair" if requirement_is_pair(item) else "single"
        print(
            f"  {item.get('id'):12} {item.get('status'):20} {surf:8} {pair:6} "
            f"{bind:8} owners={owners}  {item.get('text')}"
        )


def cmd_spec_diff(args: argparse.Namespace) -> None:
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    lines = spec_diff_lines(root, order)
    if not lines:
        print("spec-diff    none (no binding gaps vs ORDER / coverage)")
        return
    print("Binding requirements absent from ORDER / active coverage:")
    for line in lines:
        print(line)
    raise SystemExit(2)


class ContrastReport:
    """One contrast document; human one-pager + machine JSON. No second ledger."""

    NEXT_BLOCKED = (
        "pack gaps, or of spec --verified-contract ID [--both-sides] "
        "after exercising the public surface (not only unit tests)"
    )
    NEXT_RESOLVED = "done belongs to the slice; closed belongs to the SPEC (of close)"
    SKIP_LINE = "CLOSE SKIP (no SPEC; legacy field)"

    @staticmethod
    def document(root: Path, order: dict[str, Any]) -> dict[str, Any]:
        spec = spec_path(root)
        data = load_requirements(root)
        counts = requirement_counts(data)
        by_id = {
            str(item.get("id")): item
            for item in (data.get("requirements") or [])
            if isinstance(item, dict)
        }
        rows: list[dict[str, Any]] = []
        for verdict, rid, text in contrast_rows(root):
            item = by_id.get(rid) or {}
            rows.append(
                {
                    "id": rid,
                    "verdict": verdict,
                    "cite": requirement_source_cite(item),
                    "text": text[:80],
                    "blocking": not requirement_close_ok(item),
                }
            )
        errors = requirement_coverage_errors(root)
        spec_ok = spec.is_file()
        digest = sha256_text(read_spec_text(root)) if spec_ok else ""
        if not spec_ok and counts["total"] == 0:
            gate = "CLOSE_SKIP"
            verdict = "RESOLVED"
            ok = True
            nxt = ""
        elif errors:
            gate = "CLOSE_BLOCKED"
            verdict = "OPEN"
            ok = False
            nxt = ContrastReport.NEXT_BLOCKED
        else:
            gate = "RESOLVED"
            verdict = "RESOLVED"
            ok = True
            nxt = ContrastReport.NEXT_RESOLVED
        return {
            "spec": FIELD_SPEC_MD if spec_ok else "",
            "spec_hash": digest,
            "intent": truncate_slice(order.get("mission") or "", 80),
            "gate": gate,
            "verdict": verdict,
            "ok": ok,
            "coverage": counts,
            "rows": rows,
            "errors": errors,
            "next": nxt,
        }

    @staticmethod
    def machine(doc: dict[str, Any]) -> dict[str, Any]:
        rows = list(doc.get("rows") or [])
        return {
            "v": 1,
            "blocking": [str(r.get("id") or "") for r in rows if r.get("blocking")],
            "coverage": doc.get("coverage") or {},
            "errors": list(doc.get("errors") or []),
            "gate": str(doc.get("gate") or ""),
            "intent": str(doc.get("intent") or ""),
            "next": str(doc.get("next") or ""),
            "ok": bool(doc.get("ok")),
            "rows": rows,
            "spec": str(doc.get("spec") or ""),
            "spec_hash": str(doc.get("spec_hash") or ""),
            "verdict": str(doc.get("verdict") or ""),
        }

    @staticmethod
    def event_fields(doc: dict[str, Any]) -> dict[str, Any]:
        payload = ContrastReport.machine(doc)
        payload.pop("v", None)
        return payload

    @staticmethod
    def human(doc: dict[str, Any]) -> str:
        lines = ["Intent vs Delivered", ""]
        digest = str(doc.get("spec_hash") or "")
        spec = str(doc.get("spec") or "")
        if spec:
            lines.append(f"spec        {spec}  hash={digest[:12]}…")
        else:
            lines.append("spec        missing — of init --source-file (verbatim brief)")
        lines.append(f"intent      {doc.get('intent') or ''}")
        gate = str(doc.get("gate") or "")
        gate_label = {
            "CLOSE_BLOCKED": "CLOSE BLOCKED",
            "CLOSE_SKIP": "CLOSE SKIP",
            "RESOLVED": "RESOLVED",
        }.get(gate, gate)
        lines.append(f"gate        {gate_label}")
        blocking = [
            str(r.get("id") or "")
            for r in (doc.get("rows") or [])
            if r.get("blocking")
        ]
        lines.append(f"blocking    {' '.join(blocking) if blocking else 'none'}")
        lines.append("")
        rows = list(doc.get("rows") or [])
        if rows:
            for row in rows:
                cite = str(row.get("cite") or "")
                extra = f"{cite} " if cite else ""
                rid = str(row.get("id") or "")
                verdict = str(row.get("verdict") or "")
                text = str(row.get("text") or "")
                lines.append(f"{verdict:20} {rid:12} {extra}{text}")
            lines.append("")
        counts = doc.get("coverage") or {}
        lines.append(
            f"coverage: {counts.get('owned', 0)}/{counts.get('total', 0)} assigned  "
            f"verified_contract: {counts.get('verified_contract', 0)}/{counts.get('total', 0)}  "
            f"verified_internal: {counts.get('verified_internal', 0)}/{counts.get('total', 0)}"
        )
        if gate == "CLOSE_SKIP":
            lines.append(ContrastReport.SKIP_LINE)
        elif gate == "CLOSE_BLOCKED":
            lines.append("CLOSE BLOCKED")
            nxt = str(doc.get("next") or "")
            if nxt:
                lines.append(f"next: {nxt}")
            for err in doc.get("errors") or []:
                lines.append(f"error       {err}")
        else:
            lines.append("RESOLVED")
            nxt = str(doc.get("next") or "")
            if nxt:
                lines.append(nxt)
        return "\n".join(lines) + "\n"

    @staticmethod
    def open(doc: dict[str, Any]) -> bool:
        return str(doc.get("gate") or "") == "CLOSE_BLOCKED"

    @staticmethod
    def emit(doc: dict[str, Any], *, machine: bool = False) -> bool:
        print(ContrastReport.human(doc), end="")
        if machine:
            print(json.dumps(ContrastReport.machine(doc), sort_keys=True))
        return ContrastReport.open(doc)


def print_contrast_report(
    root: Path, order: dict[str, Any], *, machine: bool = False
) -> bool:
    """Print Intent vs Delivered. Return True if the SPEC loop is still open."""
    return ContrastReport.emit(ContrastReport.document(root, order), machine=machine)


def cmd_contrast(args: argparse.Namespace) -> None:
    """Review gate: original brief vs coverage. Does not edit product or ORDER."""
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    doc = ContrastReport.document(root, order)
    blocked = ContrastReport.emit(doc, machine=True)
    emit_event("contrast", **ContrastReport.event_fields(doc))
    if blocked:
        raise SystemExit(2)


class CloseProof:
    """Durable close artifact. Written in the same WAL generation as ORDER."""

    FILENAME = "CLOSE.json"

    @staticmethod
    def path(root: Path) -> Path:
        return field_home(root) / CloseProof.FILENAME

    @staticmethod
    def document(order: dict[str, Any]) -> dict[str, Any]:
        return {
            "v": 1,
            "verdict": "RESOLVED",
            "spec_closed": True,
            "done_when_closed": True,
            "spec_hash": str(order.get("spec_hash") or ""),
            "order_id": str(order.get("id") or ""),
            "rev": int(order.get("rev") or 0),
            "phase": str(order.get("phase") or ""),
            "closed_at": utc_now(),
        }

    @staticmethod
    def complete(root: Path, order: dict[str, Any]) -> bool:
        return bool(order.get("spec_closed")) and done_when_closed(order) and field_is_file(
            CloseProof.path(root)
        )

    @staticmethod
    def stamp(root: Path, order: dict[str, Any]) -> None:
        DoneWhenLint.refuse_close(order)
        mark_done_when_closed(order)
        order["spec_closed"] = True
        order["rev"] = int(order["rev"]) + 1
        save_order(order, root)
        dump_json(CloseProof.path(root), CloseProof.document(order))


def cmd_close(args: argparse.Namespace) -> None:
    """Stamp SPEC closed. Refused while contrast is OPEN. Slice done ≠ SPEC closed."""
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    if print_contrast_report(root, order):
        die(
            "of close refused: binding FAILED/MISSING/DELIVERED/"
            "VERIFIED_INTERNAL/PAIR remain"
        )
    if not spec_path(root).is_file():
        print("close       skipped (no SPEC)")
        return
    if CloseProof.complete(root, order):
        print("close       already spec_closed")
        return
    repaired = bool(order.get("spec_closed"))
    CloseProof.stamp(root, order)
    snapshot_session(root, "close")
    emit_event(
        "close",
        rev=int(order["rev"]),
        spec_hash=str(order.get("spec_hash") or "")[:12],
        done_when_closed=True,
        ok=True,
    )
    label = "REPAIRED" if repaired else "CLOSED"
    print(
        f"{label}      spec_hash={str(order.get('spec_hash') or '')[:12]}…  "
        f"rev={order['rev']}  proof={CloseProof.FILENAME}"
    )


EVAL_FIXTURES: dict[str, Any] = {}


def _register_eval_fixture(name: str):
    def decorator(fn):
        EVAL_FIXTURES[name] = fn
        return fn
    return decorator


class EvalFileAssert:
    """JSON or text payload for eval file_contains. Not a second engine."""

    @staticmethod
    def payload(path: Path) -> str:
        raw = field_read_text(path)
        if raw is None:
            die(f"missing {path}")
        try:
            return json.dumps(json.loads(raw))
        except json.JSONDecodeError:
            return raw


def eval_run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    return subprocess.run(
        [sys.executable, str(kernel_repo_root() / "scripts" / "of.py"), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class EvalInvariantSetup:
    """Shared writers for adversarial recovery fixtures. Not a second engine."""

    EXPECTED = Path("evals/expected/mission-rewrite-refused.json")

    @staticmethod
    def load_expected() -> dict[str, Any]:
        return load_json(kernel_repo_root() / EvalInvariantSetup.EXPECTED)

    @staticmethod
    def require_ok(proc: subprocess.CompletedProcess[str], label: str) -> None:
        if proc.returncode != 0:
            die(f"eval fixture {label} failed: {proc.stderr or proc.stdout}")

    @staticmethod
    def write_bound_residual(
        root: Path,
        child_id: str,
        *,
        status: str = "done",
        wants: list[str] | None = None,
        patch: dict[str, Any] | None = None,
        evidence: str = "eval residual names the check",
        result_text: str = "eval result\n",
        wave: int = 1,
    ) -> None:
        pkt_path = wave_dir(wave, root) / "packets" / f"{child_id}.json"
        packet = load_json(pkt_path)
        residual = load_json(
            kernel_repo_root() / "assets" / "fixtures" / "residual.done.json"
        )
        for key in PACKET_IDENTITY_FIELDS:
            residual[key] = packet[key]
        residual["status"] = status
        residual["role"] = packet.get("role") or residual.get("role")
        rem = residual.setdefault("residual", {})
        rem["wants_to_change"] = list(wants or [])
        rem["evidence"] = evidence
        rem["proposed_patch"] = patch
        result = root / ".orderfield" / "work" / "scratch" / child_id / "result.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(result_text, encoding="utf-8")
        residual["result_ref"] = result.relative_to(root).as_posix()
        dest = root / str(packet["residual_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dump_json(dest, residual)

    @staticmethod
    def setup_pack_exclusivity(root: Path) -> None:
        """Alice owns ALPHA-001 and slice/alice.py. BETA-001 stays unowned."""
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "eval pack exclusivity",
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        for req_id, text in (
            ("ALPHA-001", "alice exclusive slice"),
            ("BETA-001", "still unowned after alice packs"),
        ):
            added = eval_run_of(
                root,
                "spec",
                "--add",
                req_id,
                "--text",
                text,
                "--surface",
                "contract",
            )
            EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
        packed = eval_run_of(
            root,
            "pack",
            "--slice",
            "alice exclusive",
            "--role",
            "implementer",
            "--child-id",
            "alice",
            "--owns-path",
            "slice/alice.py",
            "--owns-requirement",
            "ALPHA-001",
        )
        EvalInvariantSetup.require_ok(packed, "pack alice")


def eval_write_done_residual(root: Path, child_id: str, wave: int = 1) -> None:
    EvalInvariantSetup.write_bound_residual(
        root,
        child_id,
        wave=wave,
        evidence="done residual for recovery fixture",
        result_text="done\n",
    )


def eval_pack_child(
    root: Path,
    child_id: str,
    owns_path: str,
    req_id: str,
    slice_text: str,
) -> None:
    r = eval_run_of(
        root,
        "pack",
        "--slice",
        slice_text,
        "--role",
        "implementer",
        "--child-id",
        child_id,
        "--owns-path",
        owns_path,
        "--owns-requirement",
        req_id,
    )
    if r.returncode != 0:
        die(f"eval fixture pack {child_id} failed: {r.stderr or r.stdout}")


@_register_eval_fixture("recovery_quarry_dirty")
def eval_setup_recovery_quarry_dirty(root: Path) -> None:
    r = eval_run_of(
        root,
        "init",
        "--mission",
        "build quarry append-only log",
        "--phase",
        "build",
    )
    if r.returncode != 0:
        die(f"eval fixture init failed: {r.stderr or r.stdout}")
    for req_id, text in (
        ("DOMAIN-001", "domain module"),
        ("STORE-001", "store module"),
        ("CLI-001", "cli module"),
    ):
        added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
        if added.returncode != 0:
            die(f"eval fixture spec add failed: {added.stderr or added.stdout}")
    eval_pack_child(
        root, "domain", "quarry/domain.py", "DOMAIN-001", "Implement quarry/domain.py"
    )
    eval_pack_child(
        root, "store", "quarry/store.py", "STORE-001", "Implement quarry/store.py"
    )
    eval_pack_child(
        root, "cli", "quarry/cli.py", "CLI-001", "Implement quarry/cli.py"
    )
    (root / "quarry").mkdir(exist_ok=True)
    (root / "quarry" / "domain.py").write_text("# domain\n", encoding="utf-8")
    eval_write_done_residual(root, "domain")
    (root / "quarry" / "cli.py").write_text("# partial cli\n", encoding="utf-8")
    scratch = root / ".orderfield" / "work" / "scratch" / "store"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "PULSE").write_text("waiting on domain.py\n", encoding="utf-8")


@_register_eval_fixture("recovery_beacon_amnesia")
def eval_setup_recovery_beacon_amnesia(root: Path) -> None:
    r = eval_run_of(
        root,
        "init",
        "--mission",
        "beacon append-only log",
        "--phase",
        "build",
    )
    if r.returncode != 0:
        die(f"eval fixture init failed: {r.stderr or r.stdout}")
    for req_id, text in (
        ("DOMAIN-001", "domain module"),
        ("STORE-001", "store module"),
        ("CLI-001", "cli module"),
        ("HTTP-001", "http module"),
    ):
        added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
        if added.returncode != 0:
            die(f"eval fixture spec add failed: {added.stderr or added.stdout}")
    for child_id, path, req_id in (
        ("domain", "beacon/domain.py", "DOMAIN-001"),
        ("store", "beacon/store.py", "STORE-001"),
        ("cli", "beacon/cli.py", "CLI-001"),
        ("http", "beacon/http_api.py", "HTTP-001"),
    ):
        eval_pack_child(root, child_id, path, req_id, f"Implement {path}")
    (root / "beacon").mkdir(exist_ok=True)
    (root / "beacon" / "domain.py").write_text("# domain\n", encoding="utf-8")
    eval_write_done_residual(root, "domain")
    (root / "beacon" / "cli.py").write_text("# cli stub\n", encoding="utf-8")
    (root / "beacon" / "http_api.py").write_text("# http stub\n", encoding="utf-8")


@_register_eval_fixture("recovery_contrast_close")
def eval_setup_recovery_contrast_close(root: Path) -> None:
    r = eval_run_of(
        root,
        "init",
        "--mission",
        "eval contrast gate",
        "--phase",
        "explore",
        "--source",
        "eval contrast gate: internal index ALG-001",
    )
    if r.returncode != 0:
        die(f"eval fixture init failed: {r.stderr or r.stdout}")
    added = eval_run_of(
        root,
        "spec",
        "--add",
        "ALG-001",
        "--text",
        "use an in-memory index for lookups",
        "--surface",
        "internal",
    )
    if added.returncode != 0:
        die(f"eval fixture spec add failed: {added.stderr or added.stdout}")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "implement index",
        "--role",
        "implementer",
        "--child-id",
        "imp1",
        "--owns-requirement",
        "ALG-001",
    )
    if packed.returncode != 0:
        die(f"eval fixture pack failed: {packed.stderr or packed.stdout}")


@_register_eval_fixture("recovery_mission_rewrite")
def eval_setup_recovery_mission_rewrite(root: Path) -> None:
    expected = EvalInvariantSetup.load_expected()
    init = eval_run_of(
        root,
        "init",
        "--mission",
        str(expected["mission"]),
        "--phase",
        str(expected["phase"]),
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "map options; do not rewrite the field",
        "--role",
        "explorer",
        "--child-id",
        "explorer_demo",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "explorer_demo",
        status="threshold",
        wants=["mission", "phase", "constraints", "done_when"],
        evidence=(
            "threshold: the field is insufficient; residual proposes a silent "
            "rewrite of mission, phase, constraints, and done-when"
        ),
        patch={
            "mission": expected["stolen_mission"],
            "phase": expected["stolen_phase"],
            "constraints": [expected["stolen_constraint"]],
            "done_when": [expected["stolen_done_when"]],
            "spec_closed": True,
        },
    )


@_register_eval_fixture("recovery_contrast_close_contract")
def eval_setup_recovery_contrast_close_contract(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval contract close gate",
        "--phase",
        "build",
        "--source",
        "eval contract close: CLI-001 python -m evalcli status exits 0",
    )
    EvalInvariantSetup.require_ok(init, "init")
    added = eval_run_of(
        root,
        "spec",
        "--add",
        "CLI-001",
        "--text",
        "python -m evalcli status exits 0",
        "--surface",
        "contract",
    )
    EvalInvariantSetup.require_ok(added, "spec add")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "implement evalcli status",
        "--role",
        "implementer",
        "--child-id",
        "imp1",
        "--owns-requirement",
        "CLI-001",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "imp1",
        evidence=(
            "CLI-001 implementer residual; child-forged verified_contract and "
            "spec_closed must not stamp close"
        ),
        patch={
            "requirements_verified": ["CLI-001"],
            "requirements_verified_contract": ["CLI-001"],
            "spec_closed": True,
            "mission": "child stole the mission",
        },
    )


@_register_eval_fixture("recovery_slogan_evidence")
def eval_setup_recovery_slogan_evidence(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval slogan evidence gate",
        "--phase",
        "verify",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "contrast public surface",
        "--role",
        "verifier",
        "--child-id",
        "v1",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "v1",
        evidence="all tests passed",
        result_text="transcript\n",
    )


@_register_eval_fixture("recovery_budget_seconds")
def eval_setup_recovery_budget_seconds(root: Path) -> None:
    """Empty explore field. Pack/spawn steps prove budget.seconds honesty."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval budget seconds honesty",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")


class WaveReportQualityEval:
    """Wave-1 field whose residual is a chat dump. Collect must refuse it."""

    DUMP_MARK = "here is the full conversation"
    DUMP_EVIDENCE = (
        "Human: please implement the slice and paste the transcript\n"
        "Assistant: I'll start by exploring the repo now\n"
        "Human: also dump the chat into the residual\n"
        f"Assistant: done, {DUMP_MARK}\n"
    )
    STRUCTURED_EVIDENCE = (
        "CLI-001 python -m of eval names the structured close-out"
    )

    @staticmethod
    def setup(root: Path, *, dump: bool = True) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "eval wave-report quality gate",
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        packed = eval_run_of(
            root,
            "pack",
            "--slice",
            "write a structured residual, not a chat dump",
            "--role",
            "implementer",
            "--child-id",
            "imp1",
        )
        EvalInvariantSetup.require_ok(packed, "pack")
        WaveReportQualityEval.write_residual(root, dump=dump)

    @staticmethod
    def write_residual(root: Path, *, dump: bool) -> None:
        evidence = (
            WaveReportQualityEval.DUMP_EVIDENCE
            if dump
            else WaveReportQualityEval.STRUCTURED_EVIDENCE
        )
        EvalInvariantSetup.write_bound_residual(
            root,
            "imp1",
            evidence=evidence,
            result_text="structured result\n",
        )


class MidFlightAmendEval:
    """Wave-1 in-flight field. Eval steps prove amend+patch land on wave 2."""

    ORIGINAL = (
        "Long-task mid-flight amend.\n"
        "W1-001 implements the first wave.\n"
        "W2-001 implements the second wave after the dated amend.\n"
    )
    AMEND = (
        "Keep the original brief. Also require a write log dated on each persist."
    )
    CONSTRAINT = "next packet must carry the dated amend"

    @staticmethod
    def setup(root: Path) -> None:
        brief = root / "brief.md"
        brief.write_text(MidFlightAmendEval.ORIGINAL, encoding="utf-8")
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "long-task mid-flight amend",
            "--phase",
            "build",
            "--source-file",
            str(brief),
        )
        EvalInvariantSetup.require_ok(init, "init")
        for req_id, text in (
            ("W1-001", "implements the first wave"),
            ("W2-001", "implements the second wave after the dated amend"),
        ):
            added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
            EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
        eval_pack_child(
            root, "w1", "app/w1.py", "W1-001", "Implement app/w1.py"
        )


@_register_eval_fixture("recovery_midflight_amend")
def eval_setup_recovery_midflight_amend(root: Path) -> None:
    MidFlightAmendEval.setup(root)


class ThresholdStopSpawnEval:
    """Wave-1 field with a constraints threshold. Eval steps prove the stop-spawn loop."""

    CONSTRAINT = "must cover invoicing constraints for the target country"
    EVIDENCE = "Target country requires invoicing fields ORDER never named."

    @staticmethod
    def setup(root: Path) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            "long-task threshold stop-spawn",
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        for req_id, text in (
            ("W1-001", "implements the first wave"),
            ("W2-001", "implements the second wave after the leader patch"),
        ):
            added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
            EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
        eval_pack_child(
            root, "w1", "app/w1.py", "W1-001", "Implement app/w1.py"
        )
        ThresholdStopSpawnEval.write_threshold(root)

    @staticmethod
    def write_threshold(root: Path) -> None:
        EvalInvariantSetup.write_bound_residual(
            root,
            "w1",
            status="threshold",
            wants=["constraints"],
            evidence=ThresholdStopSpawnEval.EVIDENCE,
            patch={"constraints+": [ThresholdStopSpawnEval.CONSTRAINT]},
            result_text="threshold: field is insufficient\n",
        )


@_register_eval_fixture("recovery_threshold_stop_spawn")
def eval_setup_recovery_threshold_stop_spawn(root: Path) -> None:
    ThresholdStopSpawnEval.setup(root)


@_register_eval_fixture("recovery_wave_report_quality")
def eval_setup_recovery_wave_report_quality(root: Path) -> None:
    WaveReportQualityEval.setup(root)


@_register_eval_fixture("recovery_packet_sizing")
def eval_setup_recovery_packet_sizing(root: Path) -> None:
    """Empty explore field. Pack steps prove whole-phase refuse + length note."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "eval packet sizing lint",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")


@_register_eval_fixture("recovery_pack_exclusivity")
def eval_setup_recovery_pack_exclusivity(root: Path) -> None:
    EvalInvariantSetup.setup_pack_exclusivity(root)


@_register_eval_fixture("recovery_active_field_pointer")
def eval_setup_recovery_active_field_pointer(root: Path) -> None:
    """Root explore stub plus a nested field that ACTIVE must win."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "stub explore leftover",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")
    created = eval_run_of(
        root,
        "new",
        "--mission",
        "nested real work",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(created, "new")
    from of.field import default_order, dump_bytes, json_payload_bytes

    ghost = default_order("stub explore leftover", "explore")
    dump_bytes(root / ".orderfield" / "ORDER.json", json_payload_bytes(ghost))


@_register_eval_fixture("recovery_field_roster_ux")
def eval_setup_recovery_field_roster_ux(root: Path) -> None:
    """Three sibling fields: ACTIVE on the last; roster must name it."""
    init = eval_run_of(root, "init", "--mission", "epic alpha", "--phase", "explore")
    EvalInvariantSetup.require_ok(init, "init")
    second = eval_run_of(root, "new", "--mission", "epic beta", "--phase", "build")
    EvalInvariantSetup.require_ok(second, "new beta")
    third = eval_run_of(root, "new", "--mission", "epic gamma", "--phase", "cut")
    EvalInvariantSetup.require_ok(third, "new gamma")


@_register_eval_fixture("recovery_done_when_lint")
def eval_setup_recovery_done_when_lint(root: Path) -> None:
    """Empty tree; steps exercise init/patch refuse vs accept."""
    return


@_register_eval_fixture("recovery_atomic_close")
def eval_setup_recovery_atomic_close(root: Path) -> None:
    eval_setup_recovery_contrast_close(root)


@_register_eval_fixture("recovery_skip_explore")
def eval_setup_recovery_skip_explore(root: Path) -> None:
    """Empty tree; steps exercise explore→build refuse and force-override honesty."""
    return


@_register_eval_fixture("recovery_stale_field")
def eval_setup_recovery_stale_field(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "empty waves left idle",
        "--phase",
        "explore",
    )
    EvalInvariantSetup.require_ok(init, "init")
    FieldSignal.backdate_empty(root, "2018-01-01T00:00:00Z")


@_register_eval_fixture("recovery_packed_age")
def eval_setup_recovery_packed_age(root: Path) -> None:
    """In-flight child older than 7d SLA. Status/resume name it; no unpack."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "aged packed child still in flight",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "forgotten implementer slice",
        "--role",
        "implementer",
        "--child-id",
        "worker",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    PackedAge.backdate_packet(root, "worker", "2018-01-01T00:00:00Z")


class ProcessDeathResume:
    """Spawn-host death leftovers. Resume reconstructs the live wave; no re-init."""

    CHILD = "worker"
    MISSION = "process-death live wave"
    REQ = "DEATH-001"
    DEAD_PID = 999999
    JUNK_GEN = "deadbeef"

    @staticmethod
    def packet_rel() -> str:
        return f".orderfield/waves/001/packets/{ProcessDeathResume.CHILD}.json"

    @staticmethod
    def spawn_meta_path(root: Path) -> Path:
        return (
            root
            / ".orderfield"
            / "waves"
            / "001"
            / "spawns"
            / f"{ProcessDeathResume.CHILD}.json"
        )

    @staticmethod
    def junk_wal_path(root: Path) -> Path:
        return field_home(root) / "wal" / ProcessDeathResume.JUNK_GEN

    @staticmethod
    def registry_path(root: Path) -> Path:
        return (
            root
            / ".orderfield"
            / "work"
            / "scratch"
            / "spawn-registry.json"
        )

    @staticmethod
    def setup(root: Path) -> None:
        init = eval_run_of(
            root,
            "init",
            "--mission",
            ProcessDeathResume.MISSION,
            "--phase",
            "build",
        )
        EvalInvariantSetup.require_ok(init, "init")
        added = eval_run_of(
            root,
            "spec",
            "--add",
            ProcessDeathResume.REQ,
            "--text",
            "implement after the spawn host dies",
        )
        EvalInvariantSetup.require_ok(added, "spec add")
        eval_pack_child(
            root,
            ProcessDeathResume.CHILD,
            "app/worker.py",
            ProcessDeathResume.REQ,
            "Implement app/worker.py on the live wave",
        )
        scratch = root / ".orderfield" / "work" / "scratch" / ProcessDeathResume.CHILD
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "PULSE").write_text("spawn host was writing this\n", encoding="utf-8")
        ProcessDeathResume.mark_session_spawn(root)
        ProcessDeathResume.plant_started_only_spawn(root)
        ProcessDeathResume.plant_incomplete_wal(root)
        ProcessDeathResume.plant_dead_registry(root)

    @staticmethod
    def mark_session_spawn(root: Path) -> None:
        """Commit last_cmd=spawn so resume reads CURRENT, not a live cache."""
        data = {
            "wave": 1,
            "last_cmd": "spawn",
            "in_flight": [ProcessDeathResume.CHILD],
            "updated_at": utc_now(),
        }
        require_public_schema(data, "session.schema.json", "session")
        with field_generation(root):
            dump_json(session_path(root), data)

    @staticmethod
    def plant_started_only_spawn(root: Path) -> None:
        """Live spawn meta without outcome — host died after start, before finalize."""
        meta = {
            "child_id": ProcessDeathResume.CHILD,
            "adapter": "generic",
            "wave": 1,
            "started_at": utc_now(),
        }
        dest = ProcessDeathResume.spawn_meta_path(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dump_json(dest, meta)

    @staticmethod
    def plant_incomplete_wal(root: Path) -> None:
        """Unpublished crash leftover. Resume must keep CURRENT, not this gen."""
        junk = ProcessDeathResume.junk_wal_path(root)
        junk.mkdir(parents=True, exist_ok=True)
        (junk / "state.json").write_text("{}\n", encoding="utf-8")

    @staticmethod
    def plant_dead_registry(root: Path) -> None:
        """Dead pid leftover. Resume reconstructs from packets, not PIDs."""
        dest = ProcessDeathResume.registry_path(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dump_json(
            dest,
            {
                "items": [
                    {
                        "pid": ProcessDeathResume.DEAD_PID,
                        "starttime": "1",
                        "child_id": ProcessDeathResume.CHILD,
                    }
                ]
            },
        )


@_register_eval_fixture("recovery_process_death")
def eval_setup_recovery_process_death(root: Path) -> None:
    ProcessDeathResume.setup(root)


@_register_eval_fixture("recovery_multi_day_resume")
def eval_setup_recovery_multi_day_resume(root: Path) -> None:
    """Aged wave-2 in-flight + stale session.json. Resume must reconstruct."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "multi-day live wave",
        "--phase",
        "build",
        "--origin",
        "cursor",
        "--session-id",
        "day1-owner",
    )
    EvalInvariantSetup.require_ok(init, "init")
    for req_id, text in (
        ("DOMAIN-001", "wave-1 domain"),
        ("STORE-001", "wave-1 store"),
        ("W2-001", "wave-2 implementer"),
    ):
        added = eval_run_of(root, "spec", "--add", req_id, "--text", text)
        EvalInvariantSetup.require_ok(added, f"spec add {req_id}")
    eval_pack_child(
        root, "domain", "app/domain.py", "DOMAIN-001", "Implement app/domain.py"
    )
    eval_pack_child(
        root, "store", "app/store.py", "STORE-001", "Implement app/store.py"
    )
    (root / "app").mkdir(exist_ok=True)
    (root / "app" / "domain.py").write_text("# domain\n", encoding="utf-8")
    (root / "app" / "store.py").write_text("# store\n", encoding="utf-8")
    eval_write_done_residual(root, "domain")
    eval_write_done_residual(root, "store")
    integrated = eval_run_of(root, "integrate", "--wave", "1")
    EvalInvariantSetup.require_ok(integrated, "integrate wave 1")
    nxt = eval_run_of(root, "next-wave")
    EvalInvariantSetup.require_ok(nxt, "next-wave")
    eval_pack_child(
        root, "w2", "app/w2.py", "W2-001", "Implement app/w2.py on wave 2"
    )
    scratch = root / ".orderfield" / "work" / "scratch" / "w2"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "PULSE").write_text("still the same slice\n", encoding="utf-8")
    FieldSignal.backdate_empty(root, "2018-01-01T00:00:00Z")
    stale = {
        "wave": 1,
        "last_cmd": "pack",
        "in_flight": ["domain", "store"],
        "updated_at": "2018-01-01T00:00:00Z",
    }
    require_public_schema(stale, "session.schema.json", "session")
    with field_generation(root):
        dump_json(session_path(root), stale)


@_register_eval_fixture("recovery_checkpoint_handoff")
def eval_setup_recovery_checkpoint_handoff(root: Path) -> None:
    """Multi-hour wave with STALE child. Resume must say HANDOFF, not HOLD."""
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "long-running build wave",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(init, "init")
    added = eval_run_of(root, "spec", "--add", "LONG-001", "--text", "long slice")
    EvalInvariantSetup.require_ok(added, "spec add")
    eval_pack_child(
        root, "longchild", "app/long.py", "LONG-001", "multi-hour implementer slice"
    )
    scratch = root / ".orderfield" / "work" / "scratch" / "longchild"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "PULSE").write_text("started\n", encoding="utf-8")
    import time as _time
    old_ts = _time.time() - (PULSE_STALE_MINUTES * 60 + 600)
    os.utime(scratch / "PULSE", (old_ts, old_ts))
    pkt_path = root / ".orderfield" / "waves" / "001" / "packets" / "longchild.json"
    pkt = load_json(pkt_path)
    pkt["packed_at"] = "2018-01-01T00:00:00Z"
    pkt["packet_hash"] = packet_digest(pkt)
    with field_generation(root):
        dump_json(pkt_path, pkt)


@_register_eval_fixture("recovery_verify_build")
def eval_setup_recovery_verify_build(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "keep verify; do not regress to build",
        "--phase",
        "verify",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "adversary: try to move the field back to build",
        "--role",
        "adversary",
        "--child-id",
        "adv1",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "adv1",
        status="threshold",
        wants=["phase"],
        evidence=(
            "threshold: adversary residual proposes phase=build while the "
            "field is in verify"
        ),
        patch={"phase": "build"},
    )


@_register_eval_fixture("recovery_multi_harness")
def eval_setup_recovery_multi_harness(root: Path) -> None:
    init = eval_run_of(
        root,
        "init",
        "--mission",
        "same residual under two adapters",
        "--phase",
        "build",
    )
    EvalInvariantSetup.require_ok(init, "init")
    packed = eval_run_of(
        root,
        "pack",
        "--slice",
        "implement the shared residual contract",
        "--role",
        "implementer",
        "--child-id",
        "imp1",
    )
    EvalInvariantSetup.require_ok(packed, "pack")
    EvalInvariantSetup.write_bound_residual(
        root,
        "imp1",
        evidence="done residual is adapter-neutral",
        result_text="shared residual\n",
    )


def discover_recovery_eval_specs() -> list[Path]:
    base = kernel_repo_root() / "evals" / "recovery"
    if not base.is_dir():
        return []
    return sorted(base.glob("*.eval.json"))


def run_recovery_eval_spec(spec_path: Path, *, strict: bool) -> dict[str, Any]:
    spec = load_json(spec_path)
    eval_id = str(spec.get("id") or spec_path.stem)
    fixture = str(spec.get("fixture") or "")
    setup = EVAL_FIXTURES.get(fixture)
    if not setup:
        return {
            "id": eval_id,
            "status": "failed",
            "error": f"unknown fixture {fixture!r}",
        }
    tmp = Path(tempfile.mkdtemp(prefix="of-eval-"))
    try:
        setup(tmp)
        for idx, step in enumerate(spec.get("steps") or []):
            cmd = step.get("run")
            if not cmd:
                return {
                    "id": eval_id,
                    "status": "failed",
                    "error": f"step {idx}: missing run",
                }
            argv = [cmd] if isinstance(cmd, str) else [str(c) for c in cmd]
            extra = step.get("args") or []
            if extra:
                argv.extend(str(a) for a in extra)
            proc = eval_run_of(tmp, *argv)
            want_exit = step.get("exit", 0)
            if proc.returncode != want_exit:
                return {
                    "id": eval_id,
                    "status": "failed",
                    "error": (
                        f"step {idx} {argv[0]} exit {proc.returncode} "
                        f"(want {want_exit}): {(proc.stderr or proc.stdout)[:400]}"
                    ),
                }
            blob = proc.stdout
            err = proc.stderr
            for needle in step.get("stdout_contains") or []:
                if str(needle) not in blob:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stdout missing {needle!r}",
                    }
            for needle in step.get("stdout_not_contains") or []:
                if str(needle) in blob:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stdout must not contain {needle!r}",
                    }
            for needle in step.get("stderr_contains") or []:
                if str(needle) not in err:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stderr missing {needle!r}",
                    }
            for needle in step.get("stderr_not_contains") or []:
                if str(needle) in err:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: stderr must not contain {needle!r}",
                    }
            for item in step.get("file_contains") or []:
                rel = str(item.get("path") or "")
                target = tmp / rel
                try:
                    payload = EvalFileAssert.payload(target)
                except SystemExit:
                    return {
                        "id": eval_id,
                        "status": "failed",
                        "error": f"step {idx}: missing file {rel!r}",
                    }
                for needle in item.get("contains") or []:
                    if str(needle) not in payload:
                        return {
                            "id": eval_id,
                            "status": "failed",
                            "error": f"step {idx}: {rel} missing {needle!r}",
                        }
                for needle in item.get("not_contains") or []:
                    if str(needle) in payload:
                        return {
                            "id": eval_id,
                            "status": "failed",
                            "error": f"step {idx}: {rel} must not contain {needle!r}",
                        }
        return {"id": eval_id, "status": "passed", "description": spec.get("description")}
    except SystemExit as exc:
        return {"id": eval_id, "status": "failed", "error": f"fixture/setup: {exc}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


EVAL_UNITTEST_MODULES = (
    "tests.test_kernel.CliFieldResidual",
    "tests.test_kernel.StalePackets",
    "tests.test_kernel.ResumeRecoveryBrief",
    "tests.test_kernel.MissionRewriteRefused",
    "tests.test_kernel.FieldAbandonedSignal",
    "tests.test_kernel.DurableMultiDayResume",
    "tests.test_kernel.MultiHarnessResidual",
    "tests.test_kernel.DoctorSkillVersionSkew",
    "tests.test_kernel.WaveReportQualityGate",
    "tests.test_kernel.ThresholdStopSpawn",
    "tests.test_kernel.ResumeAfterProcessDeath",
    "tests.test_kernel.PackedAgeWatchdog",
    "tests.test_kernel.ContrastReportRenderer",
    "tests.test_kernel.WaveRosterListShow",
)


def cmd_eval(args: argparse.Namespace) -> None:
    repo = kernel_repo_root()
    specs = discover_recovery_eval_specs()
    if args.list:
        for path in specs:
            spec = load_json(path)
            print(f"{spec.get('id') or path.stem}\t{path.name}\t{spec.get('description', '')}")
        if args.kernel:
            for mod in EVAL_UNITTEST_MODULES:
                print(f"{mod}\t(unittest)\tkernel manifest eval")
        return
    selected = specs
    if args.eval_id:
        needle = args.eval_id.strip().lower()
        selected = [
            p
            for p in specs
            if needle in str(load_json(p).get("id") or p.stem).lower()
            or needle in p.stem.lower()
        ]
        if not selected:
            die(f"no recovery eval matches {args.eval_id!r}")
    strict = bool(args.strict)
    passed = 0
    failed = 0
    for path in selected:
        result = run_recovery_eval_spec(path, strict=strict)
        status = result.get("status")
        label = result.get("id") or path.stem
        if status == "passed":
            passed += 1
            print(f"PASS {label}")
            emit_event("eval.completed", id=label, status="passed", ok=True)
        else:
            failed += 1
            print(f"FAIL {label}: {result.get('error')}")
            emit_event(
                "eval.completed",
                id=label,
                status="failed",
                ok=False,
                error=str(result.get("error") or ""),
            )
    if args.kernel:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", *EVAL_UNITTEST_MODULES],
            cwd=str(repo),
            env={**os.environ, "OF_NO_UPDATE_CHECK": "1"},
        )
        if proc.returncode != 0:
            failed += 1
            print("FAIL kernel unittest eval modules")
            emit_event("eval.completed", id="kernel-unittests", status="failed", ok=False)
        else:
            passed += 1
            print("PASS kernel unittest eval modules")
            emit_event("eval.completed", id="kernel-unittests", status="passed", ok=True)
    print(f"evals passed={passed} failed={failed}")
    if failed:
        raise SystemExit(1)
    if not selected and not args.kernel:
        die("no evals to run; try --list or --kernel")

