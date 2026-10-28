"""of init — create ORDER and ingest SPEC."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from of.field import (
    ActiveField,
    FIELD_SPEC_MD,
    FieldRoster,
    NestedField,
    PHASES,
    apply_origin_stamp,
    default_order,
    default_state,
    die,
    emit_event,
    field_home,
    find_root,
    of_dir,
    order_path,
    refuse_child_forge,
    resolve_init_origin,
    save_order,
    save_state,
    session_path,
    write_phase_md,
)
from of.regime import DoneWhenLint, PlanCoverage, PlanIngress
from of.pack import ensure_field_slave_md
from of.host_ram import AgentBand
from of.spec import (
    archive_previous_field,
    discard_disposable_ingest,
    extract_requirements_from_plan,
    extract_requirements_from_spec,
    merge_extracted_requirements,
    read_brief_file,
    save_requirements,
    sync_order_spec_fields,
    warn_if_deictic_brief,
    write_spec,
)


def resolve_chat_capture(args: argparse.Namespace) -> str | None:
    """Read --chat-capture-file BEFORE any field write (validation first).

    `-` reads stdin (the pasted conversation). A missing, non-UTF-8, or
    empty capture leaves the tree unchanged, like resolve_source_text.
    """
    raw = getattr(args, "chat_capture_file", None)
    if raw is None or str(raw).strip() == "":
        return None
    if str(raw).strip() == "-":
        try:
            text = sys.stdin.read()
        except OSError as exc:
            die(f"--chat-capture-file - unreadable: {exc}")
    else:
        text = read_brief_file(str(raw), flag="--chat-capture-file")
    if not str(text or "").strip():
        die("--chat-capture-file is empty; nothing to compile")
    return str(text)


def _literal_newline_escapes(text: str) -> int:
    """`\\n` used as a line break, not a path prefix (`\\new`, `\\name`)."""
    needle = "\\" + "n"
    count = 0
    start = 0
    while True:
        found = text.find(needle, start)
        if found < 0:
            return count
        nxt = text[found + 2:found + 3]
        if nxt.isalpha() or nxt == "_":
            start = found + 2
            continue
        count += 1
        start = found + 2


def warn_if_literal_newline_escapes(text: str, *, flag: str) -> bool:
    """Advisory when a brief arrived as one line of literal `\\n` (#370).

    The requirement extractor is line-based. A shell string keeps the two
    characters backslash and n, so a numbered list extracts nothing and a
    later paraphrase becomes the contract. SPEC stays the verbatim argument:
    the kernel does not unescape. Any real newline stays silent.
    """
    body = str(text or "")
    if len(body.splitlines()) > 1 or _literal_newline_escapes(body) < 2:
        return False
    print(
        f"of: note — {flag} contains literal \\n escapes and no real newline, "
        "so SPEC stays one line and list items are not extracted. "
        "Pass the conversation with --chat-capture-file - or the brief with "
        "--source-file (real newlines). Do not paraphrase into of spec --add. "
        "The SPEC was still written.",
        file=sys.stderr,
    )
    return True


def resolve_source_text(args: argparse.Namespace) -> str | None:
    """Read --source/--source-file BEFORE any field write.

    A missing or non-UTF-8 brief must leave the tree unchanged: no promotion,
    no fields/<id>/, no swallowed ingest file. UnicodeDecodeError propagates
    to the CLI error boundary (one sanitized line, exit 1)."""
    source_file = getattr(args, "source_file", None)
    source_inline = getattr(args, "source", None)
    if source_file and source_inline:
        die("pass only one of --source / --source-file")
    if source_file:
        text = read_brief_file(str(source_file), flag="--source-file")
        warn_if_deictic_brief(text, flag="--source-file")
        warn_if_literal_newline_escapes(text, flag="--source-file")
        return text
    if source_inline:
        text = str(source_inline)
        warn_if_deictic_brief(text, flag="--source")
        warn_if_literal_newline_escapes(text, flag="--source")
        return text
    return None


class DoneWhenSeed:
    """Analysis-only fields: seed binding requirements from --done-when.

    Dogfood: an explore-only field (no requirement-shaped lines in the brief)
    hit SPEC-EMPTY at close, so the leader invented SPEC text. When the SPEC
    extract is empty and the phase is explore, each --done-when line becomes
    a binding ``DONE-NNN`` requirement (origin ``added``). SPEC.md stays the
    verbatim brief.
    """

    PREFIX = "DONE"

    @staticmethod
    def requirements(
        extracted: list[dict[str, Any]], phase: str, done_when: Any
    ) -> list[dict[str, Any]]:
        if extracted or phase != "explore" or not done_when:
            return []
        from of.spec import decorate_requirement

        out: list[dict[str, Any]] = []
        for text in done_when:
            body = " ".join(str(text or "").split())
            if not body:
                continue
            out.append(
                decorate_requirement(
                    {
                        "id": f"{DoneWhenSeed.PREFIX}-{len(out) + 1:03d}",
                        "text": body,
                        "binding": True,
                        "owned_by": [],
                        "status": "unowned",
                        "origin": "added",
                    }
                )
            )
        return out


class PlanCiteExtract:
    """``of init --cite``: index the cited plan files verbatim (#362).

    The SPEC extractor runs over each cited plan file (list items with
    their wrapped / lettered lines, ID-bearing items and headings).
    ``source.path`` names the plan file, so the leader amends rather than
    transcribes. A cite with zero recognised sections warns instead of
    staying silent.
    """

    NOTE_ZERO = (
        "plan_ingest  WARN 0 requirement sections recognised in cited {where}; "
        "put list items under a Requirements / Acceptance heading or start "
        "items and headings with an ID (REQ-002, W1-R1, R1)"
    )
    NOTE_UNINDEXED = (
        "plan_ingest  note cited plan not indexed — no --source/--source-file "
        "so there is no SPEC to bind; pass the brief to index {where}"
    )

    @staticmethod
    def requirements(
        root: Path, cites: list[str] | None, existing: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[str], int]:
        """(new requirements, cited files, recognised section count)."""
        data: dict[str, Any] = {"requirements": list(existing)}
        files: list[str] = []
        recognised = 0
        for file_rel, text in PlanCiteExtract.texts(root, cites):
            files.append(file_rel)
            found = extract_requirements_from_plan(
                text, file_rel, existing=data["requirements"]
            )
            recognised += len(found) + len(PlanCoverage.sections(text))
            merge_extracted_requirements(data, found)
        return data["requirements"][len(existing):], files, recognised

    @staticmethod
    def texts(root: Path, cites: list[str] | None) -> list[tuple[str, str]]:
        """(file rel, text) for each readable *.md the cites expand to."""
        out: list[tuple[str, str]] = []
        rels = [str(r or "").strip().replace("\\", "/") for r in cites or []]
        for file_rel, path in [
            pair for rel in rels if rel for pair in PlanCoverage.expand(root, rel)
        ]:
            try:
                out.append((file_rel, path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue
        return out

    @staticmethod
    def emit(cited: list[dict[str, Any]], files: list[str], recognised: int) -> None:
        if not files:
            return
        where = " ".join(files[:3])
        if not recognised:
            print(PlanCiteExtract.NOTE_ZERO.format(where=where))
            return
        print(f"plan_ingest  {len(cited)} requirements from cited {where}")

    @staticmethod
    def emit_unindexed(root: Path, cites: list[str] | None) -> None:
        files = [rel for rel, _text in PlanCiteExtract.texts(root, cites)]
        if files:
            print(
                PlanCiteExtract.NOTE_UNINDEXED.format(where=" ".join(files[:3])),
                file=sys.stderr,
            )


def _stamp_and_write_new_field(
    args: argparse.Namespace,
    root: Path,
    *,
    force: bool,
    order: dict[str, Any] | None = None,
    source_text: str | None = None,
    chat_text: str | None = None,
    cites: list[str] | None = None,
) -> dict[str, Any]:
    phase = getattr(args, "phase", None) or "explore"
    if phase not in PHASES:
        die(f"invalid phase: {phase}")
    if not args.mission:
        die("--mission is required")
    if order is None:
        order = default_order(args.mission, phase)
    if args.done_when:
        order["done_when"] = args.done_when
    AgentBand.apply_args(order, args)
    DoneWhenLint.refuse(list(order.get("done_when") or []))
    origin_harness, origin_session = resolve_init_origin(
        getattr(args, "origin", None),
        getattr(args, "session_id", None),
    )
    if origin_harness:
        apply_origin_stamp(order, origin_harness, origin_session)
    source_file = getattr(args, "source_file", None)
    target = field_home(root)
    target.mkdir(parents=True, exist_ok=True)
    if force:
        archive_previous_field(root, target)
    (target / "work" / "scratch").mkdir(parents=True, exist_ok=True)
    (target / "waves").mkdir(parents=True, exist_ok=True)
    # Compile the mother context before PlanIngress.apply runs: explicit
    # --cite docs are pinned (folder mode + baseline see them) and the chat
    # capture is written so the chat branch pins it via capture_rels.
    for rel in list(cites or []):
        if str(rel or "").strip():
            PlanIngress.pin_cited_docs(root, order, [str(rel)])
    capture_rel = ""
    capture_sha = ""
    if chat_text is not None:
        capture_rel, capture_sha = PlanIngress.write_chat_capture(root, order, chat_text)
    if source_text is not None:
        spec_hash = write_spec(root, source_text, revise=bool(force))
        spec_reqs = extract_requirements_from_spec(source_text)
        cite_report = PlanCiteExtract.requirements(root, cites, spec_reqs)
        extracted = spec_reqs + cite_report[0]
        seeded = DoneWhenSeed.requirements(extracted, phase, args.done_when)
        extracted = extracted or seeded
        save_requirements(
            {"v": 1, "spec_hash": spec_hash, "requirements": extracted},
            root,
        )
        sync_order_spec_fields(order, root)
        print(f"spec         {FIELD_SPEC_MD}  hash={spec_hash[:12]}…")
        unowned_n = sum(
            1 for r in extracted if str(r.get("status") or "unowned") == "unowned"
        )
        label = "seeded from --done-when" if seeded and extracted is seeded else "extracted"
        print(
            f"requirements {len(extracted)} {label}  unowned {unowned_n}  "
            "(of pack --owns-requirement ID; do not implement without a packet)"
        )
        PlanCiteExtract.emit(*cite_report)
        src_path = Path(source_file) if source_file and str(source_file) != "-" else None
        ingress = PlanIngress.apply(
            root, order, source_file=src_path, source_text=source_text
        )
        discard_disposable_ingest(root, src_path, order=order)
    else:
        if chat_text is None:
            print(
                "of: note — no --source/--source-file; ORDER may compress the contract. "
                "Pass the verbatim user brief with --source or --source-file "
                "(.orderfield/ingest.md). Do not write PROMPT.md at the project root.",
                file=sys.stderr,
            )
        else:
            print(
                "of: note — --chat-capture-file is pinned; SPEC.md was not written. "
                "Pass the verbatim brief with --source or --source-file if list items "
                "should become requirements.",
                file=sys.stderr,
            )
        PlanCiteExtract.emit_unindexed(root, cites)
        ingress = PlanIngress.apply(
            root, order, source_file=source_file, source_text=source_text
        )
    # Folder mode won but a chat capture was also compiled: the chat branch
    # never ran, so pin the capture here or the conversation stays out of
    # the mother contract. Idempotent when the chat branch already pinned it.
    if capture_rel and not any(
        rel == capture_rel for rel, _digest in PlanIngress.pinned(order)
    ):
        PlanIngress.pin_source(order, capture_rel, capture_sha)
    PlanCoverage.emit_ingest(
        root, order, source_file=source_file, source_text=source_text
    )
    PlanIngress.emit(root, order, apply_doc=ingress)
    save_order(order, root)
    save_state(default_state(), root)
    write_phase_md(root, order)
    ensure_field_slave_md(root)
    ActiveField.write(root, str(order["id"]))
    sess = session_path(root)
    if sess.is_file():
        sess.unlink()
    return order


def cmd_init(args: argparse.Namespace) -> None:
    refuse_child_forge("of init")
    root = find_root()
    from of.field import (
        bind_active_field,
        list_field_homes,
        set_field_home,
    )

    homes = list_field_homes(root)
    if homes and not args.force:
        die(
            "field(s) exist; of new --mission '...' opens a sibling "
            "(or of init --force --field ID replaces one)"
        )
    source_text = resolve_source_text(args)
    chat_text = resolve_chat_capture(args)
    PlanIngress.check_cites(root, list(getattr(args, "cite", None) or []))
    if homes and args.force:
        bound = bind_active_field(
            root, getattr(args, "field_id", None), cmd="init"
        )
        if bound is None:
            die(
                "multiple fields; of init --force --field ID "
                "(or of new to open a sibling)"
            )
        target = bound
    else:
        target = of_dir(root)
        if order_path(root).exists() and not args.force:
            die(f"already exists {order_path(root)} (use --force)")
        set_field_home(target)
    order = _stamp_and_write_new_field(
        args, root, force=bool(args.force), source_text=source_text,
        chat_text=chat_text, cites=list(getattr(args, "cite", None) or []),
    )
    print(f"initialized {order_path(root)}")
    print(f"id={order['id']} rev={order['rev']} phase={order['phase']}")
    if order.get("agent_band"):
        print(f"agent_band  {AgentBand.format_line(order['agent_band'])}")
    for line in AgentBand.speak_init():
        print(line)


def cmd_new(args: argparse.Namespace) -> None:
    """Open a sibling field. Does not archive or close the others."""
    refuse_child_forge("of new")
    root = find_root()
    from of.field import (
        fields_dir,
        list_field_homes,
        promote_legacy_layout,
        set_field_home,
    )

    if not args.mission:
        die("--mission is required")
    # Validate the brief and --parent before promoting the legacy layout.
    source_text = resolve_source_text(args)
    chat_text = resolve_chat_capture(args)
    PlanIngress.check_cites(root, list(getattr(args, "cite", None) or []))
    homes = list_field_homes(root)
    if not homes:
        die("no ORDER. of init --mission '...' first; of new opens a sibling")
    parent_flag = getattr(args, "parent", None)
    parent_id = None
    if parent_flag is not None:
        parent_id = NestedField.resolve(root, parent_flag)
    promote_legacy_layout(root)
    phase = getattr(args, "phase", None) or "explore"
    order = default_order(args.mission, phase)
    if parent_id:
        NestedField.stamp(order, parent_id)
    home = fields_dir(root) / order["id"]
    if home.exists():
        die(f"field home already exists {home}")
    home.mkdir(parents=True, exist_ok=True)
    set_field_home(home)
    order = _stamp_and_write_new_field(
        args, root, force=False, order=order, source_text=source_text,
        chat_text=chat_text, cites=list(getattr(args, "cite", None) or []),
    )
    emit_event("new", field=order["id"], parent=parent_id, ok=True)
    print(f"field         {order['id']}")
    print(f"initialized {order_path(root)}")
    print(f"id={order['id']} rev={order['rev']} phase={order['phase']}")
    if order.get("agent_band"):
        print(f"agent_band  {AgentBand.format_line(order['agent_band'])}")
    for line in AgentBand.speak_init():
        print(line)
    if parent_id:
        print(f"parent        {parent_id}")
        print(NestedField.new_note(parent_id))
    else:
        print(FieldRoster.new_note())
