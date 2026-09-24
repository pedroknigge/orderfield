"""SPEC commands: spec, spec-diff, contrast, close.

`of eval` fixtures live in of.cli.eval_cmd so this file stays the
SPEC/contrast/close owner. Public CLI and `import of` names unchanged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from of.field import (
    FIELD_SPEC_MD,
    ActiveField,
    AuditPressure,
    ClosedScratch,
    Deliverable,
    DoctorSkew,
    NestedField,
    SpawnRecord,
    WaveRoster,
    die,
    dump_json,
    emit_event,
    field_generation,
    field_home,
    field_is_file,
    field_lock,
    find_root,
    load_order,
    load_state,
    refuse_child_forge,
    save_order,
    save_state,
    sha256_text,
    snapshot_session,
    spec_path,
    utc_now,
    wave_dir,
    _read_json_object,
)
from of.regime import (
    DoneWhenLint,
    PlanCoverage,
    PlanDocSync,
    PlanIngress,
    done_when_closed,
    mark_done_when_closed,
)
from of.pack import (
    PacketRevStale,
    in_flight_children,
    packed_children,
    truncate_slice,
)
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
    read_user_text,
    require_req_id,
    require_spec_intact,
    requirement_close_ok,
    requirement_counts,
    requirement_coverage_errors,
    requirement_is_pair,
    requirement_source_cite,
    requirement_surface,
    RequirementSurface,
    save_requirements,
    snapshot_spec,
    SpecDiff,
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
    surface_arg = RequirementSurface.parse(getattr(args, "surface", None))
    req_ids = [
        str(x).strip()
        for x in (getattr(args, "req_ids", None) or [])
        if str(x).strip()
    ]
    add_id_early = getattr(args, "add", None)
    if req_ids and not surface_arg:
        die(RequirementSurface.IDS_ONLY)
    if surface_arg and add_id_early and req_ids:
        die(RequirementSurface.ADD_NO_IDS)
    if surface_arg and not add_id_early and not req_ids:
        die(RequirementSurface.NEED_ID)
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
                incoming_item["surface"] = requirement_surface(incoming_item)
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
        added["surface"] = requirement_surface(added)
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
    if surface_arg and not add_id:
        for raw_id in req_ids:
            rid = require_req_id(raw_id)
            item = find_requirement(data, rid)
            if item is None:
                die(f"unknown requirement {rid}")
            old, new, wrote = RequirementSurface.apply(item, surface_arg)
            if wrote:
                changed = True
                print(f"surface     {rid} {old} -> {new}")
            else:
                print(f"surface     {rid} {new} (unchanged)")
    both_sides = bool(getattr(args, "both_sides", False))
    cite = str(getattr(args, "cite", "") or "").strip()
    verified_ids = list(getattr(args, "verified_contract", None) or [])
    if verified_ids and not cite:
        die(
            "of spec --verified-contract requires --cite <path-or-command> "
            "(receipt of the public-surface exercise)"
        )
    proof_sha = ""
    if cite and verified_ids:
        try:
            cand = (root / cite).resolve()
            cand.relative_to(root.resolve())
            if cand.is_file() and not cand.is_symlink():
                proof_sha = sha256_text(read_user_text(cand, flag="--cite"))
        except (OSError, ValueError, UnicodeDecodeError):
            proof_sha = ""
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
    for rid in verified_ids:
        item = find_requirement(data, require_req_id(rid))
        if item is None:
            die(f"unknown requirement {rid}")
        if requirement_is_pair(item) and not both_sides:
            die(
                f"{rid} is a PAIR requirement; --verified-contract needs --both-sides "
                "(exercise both sides at the public surface first)"
            )
        item["status"] = "verified_contract"
        item["proof_cite"] = cite
        if proof_sha:
            item["proof_sha"] = proof_sha
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
            state = load_state(root)
            wave = int(state.get("wave") or 1)
            live_n = len(packed_children(root, wave))
            order["rev"] = int(order["rev"]) + 1
            PlanIngress.apply(root, order, source_file=ingest_source)
            PlanCoverage.ingest(root, order)
            save_order(order, root)
            print(f"rev={order['rev']}")
            PacketRevStale.emit_note(live_n, wave)
        snapshot_session(root, "spec")
        discard_disposable_ingest(root, ingest_source, order=order if identity else None)
        if identity:
            PlanDocSync.emit(root, order)
            PlanCoverage.emit_ingest(root, order)
            PlanIngress.emit(root, order)
            PlanCoverage.emit(root, order)
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
        "after exercising the public surface (not only unit tests), "
        "or of spec --surface internal ID when the requirement was never public"
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
        blocking = [str(r.get("id") or "") for r in rows if r.get("blocking")]
        for err in doc.get("errors") or []:
            text = str(err or "")
            if text.startswith("SPEC-EMPTY"):
                if "SPEC-EMPTY" not in blocking:
                    blocking.append("SPEC-EMPTY")
            elif text and text not in blocking:
                # Keep named errors visible when no requirement rows exist.
                if not rows:
                    blocking.append(text.split(";", 1)[0].strip())
        return {
            "v": 1,
            "blocking": blocking,
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


class ContrastDiff:
    """Human narrative of SPEC vs coverage. Same facts as spec-diff + ContrastReport.

    Read-path only. No CONTRAST.json. RESOLVED is not CLOSED. ORDER_OMISSION
    can remain after the close gate is RESOLVED — the narrative names that split.
    """

    KIND = "contrast.diff"
    HEADER = "Contrast diff"
    NONE = "no binding gaps vs ORDER / coverage"
    SKIP = "no SPEC; legacy field — contrast does not invent requirements"
    GATE_RESOLVED_GAPS = (
        "close gate is RESOLVED; spec-diff still names the gaps above"
    )
    THEATER = (
        "mission complete",
        "all delivered",
        "all requirements delivered",
        "ready to ship",
        "all tests passed",
        "CLOSED",
    )
    GATE_LABEL = {
        "CLOSE_BLOCKED": "CLOSE BLOCKED",
        "CLOSE_SKIP": "CLOSE SKIP",
        "RESOLVED": "RESOLVED",
    }
    VERDICT_LINE = {
        "MISSING": "{id} is MISSING (unowned or not started){cite}.",
        "DELIVERED": "{id} is DELIVERED (owned; not close-ok){cite}.",
        "VERIFIED_INTERNAL": (
            "{id} is VERIFIED_INTERNAL (not the public contract){cite}."
        ),
        "VERIFIED_CONTRACT": "{id} is VERIFIED_CONTRACT{cite}.",
        "PAIR": "{id} is PAIR (both sides unchecked){cite}.",
        "FAILED": "{id} is FAILED{cite}.",
    }
    FLAG_LINE = {
        "UNOWNED": "{id} is unowned. Pack with --owns-requirement {id}.",
        "UNVERIFIED": (
            "{id} is unverified. A public surface cannot close until "
            "of spec --verified-contract {id}."
        ),
        "UNVERIFIED_INTERNAL": (
            "{id} is unverified. Internal close is of spec --verified-internal {id}."
        ),
        "VERIFIED_INTERNAL": (
            "{id} is VERIFIED_INTERNAL only. That is not the public contract. "
            "If it was never public: of spec --surface internal {id}."
        ),
        "PAIR": (
            "{id} is pair-shaped; both sides are unchecked. "
            "of spec --verified-contract {id} --both-sides."
        ),
        "FAILED": "{id} is FAILED.",
        "ORDER_OMISSION": (
            "{id} is an ORDER omission — the requirement text is not in "
            "mission, constraints, or done_when."
        ),
    }

    @staticmethod
    def theater(text: str) -> list[str]:
        hits: list[str] = []
        for phrase in ContrastDiff.THEATER:
            if phrase in text:
                hits.append(phrase)
        return hits

    @staticmethod
    def document(
        root: Path,
        order: dict[str, Any],
        contrast: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = contrast if contrast is not None else ContrastReport.document(
            root, order
        )
        rows = list(report.get("rows") or [])
        return {
            "v": 1,
            "kind": ContrastDiff.KIND,
            "gate": str(report.get("gate") or ""),
            "verdict": str(report.get("verdict") or ""),
            "ok": bool(report.get("ok")),
            "intent": str(report.get("intent") or ""),
            "blocking": [
                str(r.get("id") or "") for r in rows if r.get("blocking")
            ],
            "rows": rows,
            "gaps": SpecDiff.rows(root, order),
            "next": str(report.get("next") or ""),
        }

    @staticmethod
    def _cite(row: dict[str, Any]) -> str:
        cite = str(row.get("cite") or "").strip()
        text = str(row.get("text") or "").strip()
        parts: list[str] = []
        if cite:
            parts.append(cite)
        if text:
            parts.append(text)
        if not parts:
            return ""
        return " — " + " — ".join(parts)

    @staticmethod
    def human(doc: dict[str, Any]) -> str:
        gate = str(doc.get("gate") or "")
        gate_label = ContrastDiff.GATE_LABEL.get(gate, gate)
        blocking = [str(x) for x in (doc.get("blocking") or []) if str(x)]
        lines = [
            ContrastDiff.HEADER,
            "",
            f"intent      {doc.get('intent') or ''}",
            f"gate        {gate_label}",
            f"blocking    {' '.join(blocking) if blocking else 'none'}",
            "",
        ]
        for row in doc.get("rows") or []:
            rid = str(row.get("id") or "?")
            verdict = str(row.get("verdict") or "")
            tmpl = ContrastDiff.VERDICT_LINE.get(verdict)
            cite = ContrastDiff._cite(row)
            if tmpl:
                lines.append(tmpl.format(id=rid, cite=cite))
            else:
                lines.append(f"{rid} is {verdict}{cite}.")
        seen: set[tuple[str, str]] = set()
        for gap in doc.get("gaps") or []:
            rid = str(gap.get("id") or "?")
            for flag in gap.get("flags") or []:
                seen_key = (rid, str(flag))
                if seen_key in seen:
                    continue
                seen.add(seen_key)
                line_key = str(flag)
                if (
                    line_key == "UNVERIFIED"
                    and str(gap.get("surface") or "") == "internal"
                ):
                    line_key = "UNVERIFIED_INTERNAL"
                tmpl = ContrastDiff.FLAG_LINE.get(line_key)
                if tmpl:
                    lines.append(tmpl.format(id=rid))
        gaps = list(doc.get("gaps") or [])
        if not gaps:
            if gate == "CLOSE_SKIP":
                lines.append(ContrastDiff.SKIP)
            else:
                lines.append(ContrastDiff.NONE)
        elif gate == "RESOLVED":
            lines.append(ContrastDiff.GATE_RESOLVED_GAPS)
        nxt = str(doc.get("next") or "")
        if nxt:
            lines.append(f"next: {nxt}")
        text = "\n".join(lines) + "\n"
        hits = ContrastDiff.theater(text)
        if hits:
            die(f"contrast --diff theater: {', '.join(hits)}")
        return text


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
    if getattr(args, "diff", False):
        print(ContrastDiff.human(ContrastDiff.document(root, order, doc)), end="")
        print(json.dumps(ContrastReport.machine(doc), sort_keys=True))
        blocked = ContrastReport.open(doc)
    else:
        blocked = ContrastReport.emit(doc, machine=True)
    emit_event("contrast", **ContrastReport.event_fields(doc))
    if blocked:
        raise SystemExit(2)


class EvaluatorPacket:
    """Fresh-context review packet status. Not a close gate.

    Consent lives on ORDER.evaluator_consent (yes|no). Absent is
    unset — not ask. After an implementer wave settles
    (in_flight=0, published residual, not yet integrated), stored
    yes packs both roles on that wave residual before next-wave.
    Stored no skips. Review refuse is HOLD. Checklist prints
    whether those packets exist. Reuses WaveRoster roles. No new
    role, no of merge, no supervisor. CloseChecklist.ok stays
    contrast + residual. #280 reads ORDER.evaluator_consent.
    """

    KIND = "evaluator"
    KEY = "evaluator_consent"
    VALUES = ("yes", "no")
    REVIEW_ROLES = ("adversary", "verifier")
    CONSENT_YES = "yes"
    CONSENT_NO = "no"
    CONSENT_UNSET = "unset"
    REFUSE_STATUSES = frozenset(
        {"threshold", "escalate_up", "failed", "blocked"}
    )
    STATUS_ASK = "ask"
    STATUS_SKIP = "skip"
    STATUS_UNSET = "unset"
    STATUS_REFUSE = "refuse"
    STATUS_LANDED = "landed"
    STATUS_IN_FLIGHT = "in-flight"
    ASK_NEXT = "of pack --role adversary and --role verifier"
    PATCH_NEXT = "of patch --evaluator-consent yes|no"
    HOLD_DETAIL = "review refused; do not next-wave"
    SPEAK_ASK = "stored yes: pack+spawn both on this wave residual before next-wave"
    SPEAK_SKIP = "stored no: contrast then close --checklist"
    SPEAK_UNSET = "missing evaluator_consent; of patch --evaluator-consent yes|no"
    SPEAK_REFUSE = "review refused; HOLD — do not next-wave"
    SPEAK_IN_FLIGHT = "review packet in flight; flying is not closed"
    SPEAK_LANDED = "review packet landed; self-praise is not review"
    SETTLE_ACTIONS = frozenset({"collect", "integrate", "pack"})

    @staticmethod
    def consent_of(order: dict[str, Any] | None) -> str:
        raw = "" if not isinstance(order, dict) else order.get(EvaluatorPacket.KEY)
        value = str(raw or "").strip().lower()
        return value if value in EvaluatorPacket.VALUES else ""

    @staticmethod
    def normalize(raw: str) -> str:
        value = str(raw or "").strip().lower()
        if value not in EvaluatorPacket.VALUES:
            die(f"--evaluator-consent must be yes or no; got {raw!r}")
        return value

    @staticmethod
    def apply_patch(order: dict[str, Any], raw: str | None) -> bool:
        if raw is None:
            return False
        value = EvaluatorPacket.normalize(raw)
        if order.get(EvaluatorPacket.KEY) == value:
            return False
        order[EvaluatorPacket.KEY] = value
        return True

    @staticmethod
    def review_errors(order: dict[str, Any] | None) -> list[str]:
        """Missing start consent is a documented fail for the evaluator path."""
        if EvaluatorPacket.consent_of(order):
            return []
        return [
            f"missing {EvaluatorPacket.KEY}; {EvaluatorPacket.PATCH_NEXT}"
        ]

    @staticmethod
    def should_pack(order: dict[str, Any] | None) -> bool:
        return EvaluatorPacket.consent_of(order) == EvaluatorPacket.CONSENT_YES

    @staticmethod
    def children(
        root: Path,
        state: dict[str, Any],
        wave: int | None = None,
    ) -> list[dict[str, str]]:
        live = WaveRoster.live_wave(state)
        numbers = (
            [int(wave)] if wave is not None else list(WaveRoster.numbers(root, state))
        )
        out: list[dict[str, str]] = []
        for n in numbers:
            facts = WaveRoster.facts(root, n, live)
            for child in facts["children"]:
                role = str(child.get("role") or "")
                if role not in EvaluatorPacket.REVIEW_ROLES:
                    continue
                cid = str(child.get("child_id") or "").strip()
                if not cid:
                    continue
                out.append(
                    {
                        "child_id": cid,
                        "role": role,
                        "status": str(child.get("status") or ""),
                        "residual_status": str(child.get("residual_status") or ""),
                    }
                )
        return out

    @staticmethod
    def due(
        root: Path,
        order: dict[str, Any],
        state: dict[str, Any],
        wave: int | None = None,
    ) -> bool:
        if order.get("spec_closed"):
            return False
        if EvaluatorPacket.consent_of(order) != EvaluatorPacket.CONSENT_YES:
            return False
        live = WaveRoster.live_wave(state)
        target = live if wave is None else int(wave)
        if field_is_file(wave_dir(int(target), root) / "report.json"):
            return False
        facts = WaveRoster.facts(root, int(target), live)
        if facts["in_flight"]:
            return False
        roles = {str(child.get("role") or "") for child in facts["children"]}
        if all(role in roles for role in EvaluatorPacket.REVIEW_ROLES):
            return False
        return any(
            child.get("status") == "done"
            and str(child.get("role") or "") not in EvaluatorPacket.REVIEW_ROLES
            for child in facts["children"]
        )

    @staticmethod
    def refused(
        root: Path,
        state: dict[str, Any],
        wave: int | None = None,
    ) -> bool:
        children = EvaluatorPacket.children(root, state, wave)
        if not children:
            return False
        if any(row.get("status") == "in-flight" for row in children):
            return False
        return any(
            row.get("residual_status") in EvaluatorPacket.REFUSE_STATUSES
            for row in children
        )

    @staticmethod
    def gate_action(
        action: str,
        root: Path,
        order: dict[str, Any],
        state: dict[str, Any],
        wave: int,
    ) -> str:
        """Idle settle: refuse HOLD; due packs both roles. No new verb."""
        if EvaluatorPacket.refused(root, state, int(wave)):
            return "hold"
        if (
            EvaluatorPacket.due(root, order, state, int(wave))
            and action in EvaluatorPacket.SETTLE_ACTIONS
        ):
            return "pack"
        return action

    @staticmethod
    def status_of(
        children: list[dict[str, str]],
        consent: str = "",
    ) -> str:
        flying = any(row.get("status") == "in-flight" for row in children)
        if (
            (not flying)
            and children
            and any(
                row.get("residual_status") in EvaluatorPacket.REFUSE_STATUSES
                for row in children
            )
        ):
            return EvaluatorPacket.STATUS_REFUSE
        if flying:
            return EvaluatorPacket.STATUS_IN_FLIGHT
        if children:
            return EvaluatorPacket.STATUS_LANDED
        if consent == EvaluatorPacket.CONSENT_NO:
            return EvaluatorPacket.STATUS_SKIP
        if consent == EvaluatorPacket.CONSENT_YES:
            return EvaluatorPacket.STATUS_ASK
        return EvaluatorPacket.STATUS_UNSET

    @staticmethod
    def speak_for(status: str) -> str:
        if status == EvaluatorPacket.STATUS_IN_FLIGHT:
            return EvaluatorPacket.SPEAK_IN_FLIGHT
        if status == EvaluatorPacket.STATUS_LANDED:
            return EvaluatorPacket.SPEAK_LANDED
        if status == EvaluatorPacket.STATUS_SKIP:
            return EvaluatorPacket.SPEAK_SKIP
        if status == EvaluatorPacket.STATUS_REFUSE:
            return EvaluatorPacket.SPEAK_REFUSE
        if status == EvaluatorPacket.STATUS_UNSET:
            return EvaluatorPacket.SPEAK_UNSET
        if status == EvaluatorPacket.STATUS_REFUSE:
            return EvaluatorPacket.SPEAK_REFUSE
        return EvaluatorPacket.SPEAK_ASK

    @staticmethod
    def speak_line(status: str = "", *, key: str = "speak", key_width: int = 12) -> str:
        text = EvaluatorPacket.speak_for(status or EvaluatorPacket.STATUS_ASK)
        return f"{key.ljust(key_width)}{text}"

    @staticmethod
    def document(
        root: Path,
        state: dict[str, Any] | None = None,
        order: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if state is None:
            state = load_state(root)
        if order is None:
            order = load_order(root)
        children = EvaluatorPacket.children(root, state)
        consent = EvaluatorPacket.consent_of(order)
        status = EvaluatorPacket.status_of(children, consent)
        due = EvaluatorPacket.due(root, order, state)
        if status == EvaluatorPacket.STATUS_ASK:
            nxt = EvaluatorPacket.ASK_NEXT
        elif status == EvaluatorPacket.STATUS_UNSET:
            nxt = EvaluatorPacket.PATCH_NEXT
        elif status == EvaluatorPacket.STATUS_REFUSE:
            nxt = EvaluatorPacket.HOLD_DETAIL
        else:
            nxt = ""
        return {
            "v": 1,
            "kind": EvaluatorPacket.KIND,
            "consent": consent,
            "due": due,
            "evaluator": status,
            "evaluator_ids": [row["child_id"] for row in children],
            "evaluator_roles": sorted({row["role"] for row in children}),
            "evaluator_children": children,
            "due": due,
            "next": nxt,
            "speak": EvaluatorPacket.speak_for(status),
        }

    @staticmethod
    def machine(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "v": 1,
            "consent": str(doc.get("consent") or ""),
            "due": bool(doc.get("due")),
            "evaluator": str(doc.get("evaluator") or EvaluatorPacket.STATUS_UNSET),
            "evaluator_ids": [str(cid) for cid in (doc.get("evaluator_ids") or [])],
            "evaluator_roles": [
                str(role) for role in (doc.get("evaluator_roles") or [])
            ],
            "due": bool(doc.get("due")),
            "kind": EvaluatorPacket.KIND,
            "next": str(doc.get("next") or ""),
            "speak": str(doc.get("speak") or EvaluatorPacket.SPEAK_UNSET),
        }

    @staticmethod
    def named(doc: dict[str, Any]) -> str:
        status = str(doc.get("evaluator") or EvaluatorPacket.STATUS_UNSET)
        if status == EvaluatorPacket.STATUS_ASK:
            return EvaluatorPacket.ASK_NEXT
        if status == EvaluatorPacket.STATUS_UNSET:
            return EvaluatorPacket.PATCH_NEXT
        if status == EvaluatorPacket.STATUS_REFUSE:
            return EvaluatorPacket.HOLD_DETAIL
        if status == EvaluatorPacket.STATUS_SKIP:
            return "stored no"
        if status == EvaluatorPacket.STATUS_REFUSE:
            return EvaluatorPacket.HOLD_DETAIL
        pairs: list[str] = []
        for row in doc.get("evaluator_children") or []:
            role = str(row.get("role") or "").strip()
            cid = str(row.get("child_id") or "").strip()
            if role and cid:
                pairs.append(f"{role}:{cid}")
            elif cid:
                pairs.append(cid)
        if pairs:
            return " ".join(pairs)
        ids = [str(cid) for cid in (doc.get("evaluator_ids") or []) if cid]
        return " ".join(ids) if ids else "-"

    @staticmethod
    def human_line(doc: dict[str, Any], *, key_width: int = 12) -> str:
        status = str(doc.get("evaluator") or EvaluatorPacket.STATUS_UNSET)
        extra = EvaluatorPacket.named(doc)
        return f"{'evaluator'.ljust(key_width)}{status}  {extra}"


class CloseChecklist:
    """Proof checklist for multi-wave close. Contrast + residual empty.

    Reuses ContrastReport + SpawnRecord.flying (started-only dominates leftover residual).
    No second ledger, no supervisor. `of close --checklist` is the dry-run;
    the write path refuses the same gaps. EvaluatorPacket is printed here as
    ask-only status — not part of ok.
    """

    KIND = "checklist"
    NEXT_READY = "of close"
    RESIDUAL_EMPTY = "empty"
    RESIDUAL_MISSING = "MISSING"
    # Claim-shipped directive: contrast + residual rows are already printed
    # above. Pair with InFlightSignal.speak_line (quote-PULSE while flying).
    SPEAK = "do not claim shipped unless contrast RESOLVED and residual empty"

    @staticmethod
    def speak_line(*, key: str = "speak", key_width: int = 12) -> str:
        return f"{key.ljust(key_width)}{CloseChecklist.SPEAK}"

    @staticmethod
    def flying(root: Path, state: dict[str, Any]) -> list[str]:
        """Packed children that are SpawnRecord.flying. Started-only dominates leftover residual."""
        ids: list[str] = []
        seen: set[str] = set()
        for n in WaveRoster.numbers(root, state):
            pdir = wave_dir(int(n), root) / "packets"
            if not pdir.is_dir():
                continue
            try:
                paths = sorted(pdir.glob("*.json"))
            except OSError:
                continue
            for path in paths:
                pkt = _read_json_object(path)
                if not isinstance(pkt, dict):
                    continue
                cid = str(pkt.get("child_id") or path.stem).strip()
                if not cid or cid in seen:
                    continue
                if SpawnRecord.flying(root, pkt):
                    seen.add(cid)
                    ids.append(cid)
        return ids

    @staticmethod
    def next_line(
        *,
        contrast_ok: bool,
        residual_empty: bool,
        live: int,
        contrast_next: str,
    ) -> str:
        parts: list[str] = []
        if not residual_empty:
            parts.append(
                f"residual MISSING — of collect --wave {live} "
                "after the child writes; flying is not closed"
            )
        if not contrast_ok:
            parts.append(contrast_next or ContrastReport.NEXT_BLOCKED)
        if not parts:
            return CloseChecklist.NEXT_READY
        return "; ".join(parts)

    @staticmethod
    def document(
        root: Path,
        order: dict[str, Any],
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if state is None:
            state = load_state(root)
        contrast = ContrastReport.document(root, order)
        flying = CloseChecklist.flying(root, state)
        residual_empty = not flying
        contrast_ok = not ContrastReport.open(contrast)
        live = WaveRoster.live_wave(state)
        waves = WaveRoster.numbers(root, state)
        gate = str(contrast.get("gate") or "")
        evaluator = EvaluatorPacket.document(root, state, order)
        return {
            "v": 1,
            "ok": contrast_ok and residual_empty,
            "kind": CloseChecklist.KIND,
            "contrast": gate,
            "contrast_ok": contrast_ok,
            "residual": (
                CloseChecklist.RESIDUAL_EMPTY
                if residual_empty
                else CloseChecklist.RESIDUAL_MISSING
            ),
            "residual_empty": residual_empty,
            "blocking": [
                str(row.get("id") or "")
                for row in (contrast.get("rows") or [])
                if row.get("blocking")
            ],
            "in_flight": len(flying),
            "in_flight_ids": flying,
            "wave": live,
            "waves": len(waves),
            "consent": evaluator.get("consent"),
            "evaluator": evaluator.get("evaluator"),
            "evaluator_ids": list(evaluator.get("evaluator_ids") or []),
            "evaluator_roles": list(evaluator.get("evaluator_roles") or []),
            "evaluator_children": list(evaluator.get("evaluator_children") or []),
            "evaluator_speak": evaluator.get("speak"),
            "next": CloseChecklist.next_line(
                contrast_ok=contrast_ok,
                residual_empty=residual_empty,
                live=live,
                contrast_next=str(contrast.get("next") or ""),
            ),
        }

    @staticmethod
    def machine(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "v": 1,
            "blocking": [str(rid) for rid in (doc.get("blocking") or [])],
            "contrast": str(doc.get("contrast") or ""),
            "contrast_ok": bool(doc.get("contrast_ok")),
            "in_flight": int(doc.get("in_flight") or 0),
            "in_flight_ids": [str(cid) for cid in (doc.get("in_flight_ids") or [])],
            "kind": CloseChecklist.KIND,
            "next": str(doc.get("next") or ""),
            "ok": bool(doc.get("ok")),
            "residual": str(doc.get("residual") or ""),
            "residual_empty": bool(doc.get("residual_empty")),
            "consent": str(doc.get("consent") or ""),
            "evaluator": str(doc.get("evaluator") or EvaluatorPacket.STATUS_UNSET),
            "evaluator_ids": [str(cid) for cid in (doc.get("evaluator_ids") or [])],
            "evaluator_roles": [
                str(role) for role in (doc.get("evaluator_roles") or [])
            ],
            "wave": int(doc.get("wave") or 0),
            "waves": int(doc.get("waves") or 0),
        }

    @staticmethod
    def event_fields(doc: dict[str, Any]) -> dict[str, Any]:
        payload = CloseChecklist.machine(doc)
        payload.pop("v", None)
        return payload

    @staticmethod
    def human(doc: dict[str, Any]) -> str:
        gate = str(doc.get("contrast") or "")
        gate_label = {
            "CLOSE_BLOCKED": "CLOSE BLOCKED",
            "CLOSE_SKIP": "CLOSE SKIP",
            "RESOLVED": "RESOLVED",
        }.get(gate, gate or "-")
        residual = str(doc.get("residual") or "")
        flying = [str(cid) for cid in (doc.get("in_flight_ids") or [])]
        if residual == CloseChecklist.RESIDUAL_MISSING and flying:
            residual_line = f"{CloseChecklist.RESIDUAL_MISSING}  {' '.join(flying)}"
        elif residual == CloseChecklist.RESIDUAL_EMPTY:
            residual_line = CloseChecklist.RESIDUAL_EMPTY
        else:
            residual_line = residual or "-"
        blocking = [str(rid) for rid in (doc.get("blocking") or []) if rid]
        lines = [
            "close checklist",
            f"contrast     {gate_label}",
            f"residual     {residual_line}",
            f"wave         {int(doc.get('wave') or 0)}  "
            f"waves {int(doc.get('waves') or 0)}  "
            f"in_flight {int(doc.get('in_flight') or 0)}",
            f"blocking     {' '.join(blocking) if blocking else 'none'}",
        ]
        nxt = str(doc.get("next") or "")
        if nxt:
            lines.append(f"next         {nxt}")
        lines.append(EvaluatorPacket.human_line(doc, key_width=12))
        lines.append(CloseChecklist.speak_line(key_width=12))
        status = str(doc.get("evaluator") or EvaluatorPacket.STATUS_UNSET)
        lines.append(EvaluatorPacket.speak_line(status, key_width=12))
        return "\n".join(lines) + "\n"

    @staticmethod
    def open(doc: dict[str, Any]) -> bool:
        return not bool(doc.get("ok"))

    @staticmethod
    def emit(doc: dict[str, Any], *, machine: bool = False) -> bool:
        print(CloseChecklist.human(doc), end="")
        if machine:
            print(json.dumps(CloseChecklist.machine(doc), sort_keys=True))
        return CloseChecklist.open(doc)

    @staticmethod
    def refuse_residual(doc: dict[str, Any]) -> None:
        ids = [str(cid) for cid in (doc.get("in_flight_ids") or []) if cid]
        named = " ".join(ids) if ids else CloseChecklist.RESIDUAL_MISSING
        die(
            f"of close refused: residual MISSING {named} "
            "(flying is not closed)"
        )


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
        DoneWhenLint.refuse_close(order, root=root)
        mark_done_when_closed(order)
        order["spec_closed"] = True
        order["rev"] = int(order["rev"]) + 1
        state = load_state(root)
        state["spawn_blocked"] = False
        with field_generation(root):
            save_order(order, root)
            save_state(state, root)
            dump_json(CloseProof.path(root), CloseProof.document(order))

    @staticmethod
    def stamp_abandoned(root: Path, order: dict[str, Any], reason: str) -> None:
        """Terminal stop. Not contrast. Not done_when. Archive can move the home."""
        text = str(reason or "").strip()
        if not text:
            die("of close --abandoned requires --reason <text>")
        order["spec_closed"] = True
        order["rev"] = int(order["rev"]) + 1
        state = load_state(root)
        state["spawn_blocked"] = True
        doc = CloseProof.document(order)
        doc["verdict"] = "ABANDONED"
        doc["reason"] = text
        doc["done_when_closed"] = False
        with field_generation(root):
            save_order(order, root)
            save_state(state, root)
            dump_json(CloseProof.path(root), doc)


def cmd_close(args: argparse.Namespace) -> None:
    """Stamp SPEC closed. Refused while contrast is OPEN or residual MISSING."""
    refuse_child_forge("of close")
    root = find_root()
    order = load_order(root)
    require_spec_intact(root, order)
    state = load_state(root)
    checklist = CloseChecklist.document(root, order, state)
    AuditPressure.emit(root)
    PlanDocSync.emit(root, order)
    PlanCoverage.emit(root, order)
    PlanIngress.emit(root, order)
    DoctorSkew.emit_teardown(root)
    if getattr(args, "abandoned", False):
        if getattr(args, "checklist", False):
            die("of close --abandoned does not take --checklist")
        reason = str(getattr(args, "reason", "") or "").strip()
        if not reason:
            die("of close --abandoned requires --reason <text>")
        wave = int(order.get("wave") or state.get("wave") or 1)
        flying = in_flight_children(root, wave)
        if flying:
            names = ", ".join(str(item.get("child_id") or "?") for item in flying)
            die(f"of close --abandoned refuses in-flight children: {names}")
        if order.get("spec_closed"):
            print("close       already spec_closed")
            return
        CloseProof.stamp_abandoned(root, order, reason)
        fid = str(order.get("id") or "")
        print(
            f"ABANDONED   rev={order['rev']}  proof={CloseProof.FILENAME}  "
            f"reason={reason}"
        )
        if fid:
            print(f"next          of gc --archive-field {fid}")
        return
    if not getattr(args, "checklist", False):
        hold = PlanCoverage.hold_close(root, order)
        if hold:
            die(hold)
        fidelity = PlanIngress.hold_close(root, order)
        if fidelity:
            die(fidelity)
    if getattr(args, "checklist", False):
        blocked = CloseChecklist.emit(checklist, machine=True)
        emit_event(
            "close",
            checklist=True,
            written=False,
            **CloseChecklist.event_fields(checklist),
        )
        if blocked:
            raise SystemExit(2)
        return
    if print_contrast_report(root, order):
        doc = ContrastReport.document(root, order)
        errors = [str(e) for e in (doc.get("errors") or []) if e]
        if errors and all(str(e).startswith("SPEC-EMPTY") for e in errors):
            die(
                "of close refused: SPEC-EMPTY — "
                "of spec --add ID --text '…' before close"
            )
        labels: list[str] = []
        for row in doc.get("rows") or []:
            if not isinstance(row, dict) or not row.get("blocking"):
                continue
            rid = str(row.get("id") or "")
            verdict = str(row.get("verdict") or "")
            if rid and verdict:
                labels.append(f"{rid} ({verdict})")
            elif rid:
                labels.append(rid)
        machine = ContrastReport.machine(doc)
        if not labels:
            labels = [str(b) for b in (machine.get("blocking") or []) if b]
        if labels:
            die(
                "of close refused: binding remain — "
                + ", ".join(labels[:12])
                + ("…" if len(labels) > 12 else "")
            )
        die(
            "of close refused: contrast OPEN — "
            + (errors[0] if errors else ContrastReport.NEXT_BLOCKED)
        )
    if not checklist["residual_empty"]:
        CloseChecklist.refuse_residual(checklist)
    if not spec_path(root).is_file():
        print("close       skipped (no SPEC)")
        return
    if CloseProof.complete(root, order):
        print("close       already spec_closed")
        Deliverable.emit(root, Deliverable.promote(root))
        ClosedScratch.emit(ClosedScratch.wipe(root))
        return
    repaired = bool(order.get("spec_closed"))
    # Promote before the stamp: a lost deliverable refuses the close.
    promoted = Deliverable.promote(root)
    CloseProof.stamp(root, order)
    wiped = ClosedScratch.wipe(root)
    returned = NestedField.return_active(root, order)
    snapshot_session(root, "close")
    emit_event(
        "close",
        rev=int(order["rev"]),
        spec_hash=str(order.get("spec_hash") or "")[:12],
        done_when_closed=True,
        parent=returned,
        ok=True,
        checklist=False,
        written=True,
        residual_empty=True,
        in_flight=0,
        scratch_wiped=wiped,
    )
    label = "REPAIRED" if repaired else "CLOSED"
    print(
        f"{label}      spec_hash={str(order.get('spec_hash') or '')[:12]}…  "
        f"rev={order['rev']}  proof={CloseProof.FILENAME}"
    )
    Deliverable.emit(root, promoted)
    ClosedScratch.emit(wiped)
    if returned:
        print(NestedField.format_return_line(returned))
    else:
        note = ActiveField.fallback_note(root, str(order.get("id") or ""))
        if note:
            print(note)

