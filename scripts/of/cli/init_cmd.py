"""of init — create ORDER and ingest SPEC."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from of.field import (
    FIELD_SPEC_MD,
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
    resolve_init_origin,
    save_order,
    save_state,
    session_path,
    write_phase_md,
)
from of.pack import ensure_field_slave_md
from of.spec import (
    archive_previous_field,
    discard_disposable_ingest,
    extract_requirements_from_spec,
    read_brief_file,
    save_requirements,
    sync_order_spec_fields,
    warn_if_deictic_brief,
    write_spec,
)


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
        return text
    if source_inline:
        text = str(source_inline)
        warn_if_deictic_brief(text, flag="--source")
        return text
    return None


def _stamp_and_write_new_field(
    args: argparse.Namespace,
    root: Path,
    *,
    force: bool,
    order: dict[str, Any] | None = None,
    source_text: str | None = None,
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
    if source_text is not None:
        spec_hash = write_spec(root, source_text, revise=bool(force))
        extracted = extract_requirements_from_spec(source_text)
        save_requirements(
            {"v": 1, "spec_hash": spec_hash, "requirements": extracted},
            root,
        )
        sync_order_spec_fields(order, root)
        print(f"spec         {FIELD_SPEC_MD}  hash={spec_hash[:12]}…")
        unowned_n = sum(
            1 for r in extracted if str(r.get("status") or "unowned") == "unowned"
        )
        print(
            f"requirements {len(extracted)} extracted  unowned {unowned_n}  "
            "(of pack --owns-requirement ID; do not implement without a packet)"
        )
        src_path = Path(source_file) if source_file and str(source_file) != "-" else None
        discard_disposable_ingest(root, src_path)
    else:
        print(
            "of: note — no --source/--source-file; ORDER may compress the contract. "
            "Pass the verbatim user brief with --source or --source-file "
            "(.orderfield/ingest.md). Do not write PROMPT.md at the project root.",
            file=sys.stderr,
        )
    save_order(order, root)
    save_state(default_state(), root)
    write_phase_md(root, order)
    ensure_field_slave_md(root)
    sess = session_path(root)
    if sess.is_file():
        sess.unlink()
    return order


def cmd_init(args: argparse.Namespace) -> None:
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
        args, root, force=bool(args.force), source_text=source_text
    )
    print(f"initialized {order_path(root)}")
    print(f"id={order['id']} rev={order['rev']} phase={order['phase']}")


def cmd_new(args: argparse.Namespace) -> None:
    """Open a sibling field. Does not archive or close the others."""
    root = find_root()
    from of.field import (
        fields_dir,
        list_field_homes,
        promote_legacy_layout,
        set_field_home,
    )

    if not args.mission:
        die("--mission is required")
    # Validate the brief before promoting the legacy layout or creating fields/<id>/.
    source_text = resolve_source_text(args)
    promote_legacy_layout(root)
    homes = list_field_homes(root)
    if not homes:
        die("no ORDER. of init --mission '...' first; of new opens a sibling")
    phase = getattr(args, "phase", None) or "explore"
    order = default_order(args.mission, phase)
    home = fields_dir(root) / order["id"]
    if home.exists():
        die(f"field home already exists {home}")
    home.mkdir(parents=True, exist_ok=True)
    set_field_home(home)
    order = _stamp_and_write_new_field(
        args, root, force=False, order=order, source_text=source_text
    )
    emit_event("new", field=order["id"], ok=True)
    print(f"field         {order['id']}")
    print(f"initialized {order_path(root)}")
    print(f"id={order['id']} rev={order['rev']} phase={order['phase']}")
