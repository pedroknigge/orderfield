"""Versioned artifact migrations: catalog, planning, and application.

SCOPE-GODSPLIT extraction from of.field. Reads and writes go through the
field helpers (this module imports of.field; of.field never imports this
module), so `of migrate` and the load path stay one migration authority.
`migrate_packet_artifact`/`apply_field_migrations` lazily import of.pack
for packet identity and validation — the same lazy edge of.field already had.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from of.field import (
    CURRENT_ARTIFACT_GENERATION,
    PROTOCOL_SLAVE_MD,
    PROTOCOL_WRITABLE_KEY,
    RootStub,
    _read_json_object,
    default_state,
    die,
    dump_json,
    field_home,
    load_json,
    order_path,
    require_public_schema,
    skill_root,
    state_path,
    strip_retired_runtime_keys,
    migrate_wave_report_artifact,
    utc_now,
)

WRITABLE_ALIAS_KEYS = ("writable_by_children", "writable_by_child")


MIGRATION_CATALOG = (
    {
        "id": "pre-0.4.2-packet-identity",
        "from": "pre-0.4.2",
        "to": "0.4.2",
        "kind": "packet",
        "description": (
            "Add packet_id, order_id, packed_at, and packet_hash to "
            "identity-free packets"
        ),
    },
    {
        "id": "pre-0.4.2-state-defaults",
        "from": "pre-0.4.2",
        "to": "0.4.2",
        "kind": "state",
        "description": (
            "Fill integration_history and phase_overrides; drop unknown keys"
        ),
    },
    {
        "id": "pre-0.4.2-report-readable",
        "from": "pre-0.4.2",
        "to": "0.4.2",
        "kind": "wave-report",
        "description": (
            "Keep pre-digest reports readable; do not invent integration hashes"
        ),
    },
    {
        "id": "protocol-writable-key",
        "from": "any",
        "to": CURRENT_ARTIFACT_GENERATION,
        "kind": "order|packet",
        "description": (
            "Map writable aliases onto workspace.writable_by_slaves; "
            "never rename SLAVE.md"
        ),
    },
    {
        "id": "retired-runtime-keys",
        "from": "any",
        "to": CURRENT_ARTIFACT_GENERATION,
        "kind": "order|packet|state|wave-report",
        "description": (
            "Drop contest, scale_up/scale_across, across caps/counters, "
            "local_budget_pct, inherited depth, and budget.tokens"
        ),
    },
    {
        "id": "root-stub-archive",
        "from": "leftover-root",
        "to": "0.7.27",
        "kind": "root-stub",
        "description": (
            "Archive leftover .orderfield/ORDER.json once fields/<id>/ "
            "exists; never silent delete"
        ),
    },
)

def normalize_workspace(workspace: Any) -> tuple[Any, list[str]]:
    """Fold writable aliases onto the frozen protocol key. Never rename SLAVE.md."""
    notes: list[str] = []
    if not isinstance(workspace, dict):
        return workspace, notes
    ws = dict(workspace)
    aliases_present = [key for key in WRITABLE_ALIAS_KEYS if key in ws]
    if PROTOCOL_WRITABLE_KEY in ws:
        for key in aliases_present:
            ws.pop(key, None)
            notes.append(f"dropped alias workspace.{key}; kept {PROTOCOL_WRITABLE_KEY}")
        return ws, notes
    if aliases_present:
        source = aliases_present[0]
        ws[PROTOCOL_WRITABLE_KEY] = ws.pop(source)
        notes.append(f"mapped workspace.{source} -> {PROTOCOL_WRITABLE_KEY}")
        for key in aliases_present[1:]:
            ws.pop(key, None)
            notes.append(f"dropped extra alias workspace.{key}")
    return ws, notes


def migrate_packet_artifact(packet: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Upgrade a packet to the current identity contract. Idempotent."""
    from of.pack import packet_digest, packet_has_identity
    notes: list[str] = []
    out = dict(packet)
    budget = out.get("budget")
    if isinstance(budget, dict) and "tokens" in budget:
        budget = dict(budget)
        budget.pop("tokens", None)
        out["budget"] = budget
        notes.append("dropped packet budget.tokens")
    embedded = out.get("order") if isinstance(out.get("order"), dict) else {}
    if embedded:
        embedded, retired = strip_retired_runtime_keys(embedded)
        if retired:
            out["order"] = embedded
            notes.extend(retired)
    order_ws = embedded.get("workspace")
    new_ws, ws_notes = normalize_workspace(order_ws)
    if ws_notes and isinstance(embedded, dict):
        embedded = dict(embedded)
        embedded["workspace"] = new_ws
        out["order"] = embedded
        notes.extend(ws_notes)
    mutated = bool(notes)
    if not packet_has_identity(out):
        child_id = str(out.get("child_id") or "")
        if not child_id or "wave" not in out or "role" not in out:
            notes.append("skipped identity; packet missing wave/child_id/role")
            return out, notes
        order_id = out.get("order_id") or (
            embedded.get("id") if isinstance(embedded, dict) else None
        )
        if not order_id:
            notes.append("skipped identity; packet missing order_id")
            return out, notes
        if "packet_id" not in out:
            out["packet_id"] = f"pkt_{uuid.uuid4().hex}"
            notes.append(f"added packet_id for {child_id}")
        if "order_id" not in out:
            out["order_id"] = order_id
            notes.append("added order_id from embedded ORDER")
        if "packed_at" not in out:
            out["packed_at"] = utc_now()
            notes.append("added packed_at")
        out["packet_hash"] = packet_digest(out)
        notes.append("computed packet_hash")
    elif out.get("packet_hash") != packet_digest(out):
        # Only re-hash when a migration step (workspace normalize or a retired
        # key) actually rewrote the packet AND the stored hash matched the
        # pre-migration bytes. A plain mismatch is child tamper, not a migration
        # artifact: leave it so validate_packet flags it INVALID instead of
        # signing the child's edit.
        if mutated and packet.get("packet_hash") == packet_digest(packet):
            out["packet_hash"] = packet_digest(out)
            notes.append("recomputed packet_hash after protocol-key rewrite")
        else:
            notes.append("refused: packet_hash mismatch is not a migration (RESTORE)")
            return dict(packet), notes
    return out, notes


def migrate_state_artifact(state: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    schema = load_json(skill_root() / "schemas" / "state.schema.json")
    allowed = set((schema.get("properties") or {}) if isinstance(schema, dict) else [])
    base = default_state()
    incoming = dict(state)
    extras = sorted(set(incoming) - allowed) if allowed else []
    if extras:
        for key in extras:
            incoming.pop(key, None)
        notes.append(f"dropped unknown state keys {extras}")
    if incoming.get("last_regime") in ("scale_up", "scale_across"):
        incoming["last_regime"] = "hold"
        notes.append("remapped retired state.last_regime to hold")
    for key, value in base.items():
        if key not in incoming:
            incoming[key] = value
            notes.append(f"filled state.{key}")
    return incoming, notes


def migrate_residual_artifact(
    residual: dict[str, Any],
    packet: dict[str, Any] | None,
    *,
    previous_packet_hash: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    from of.pack import PACKET_IDENTITY_FIELDS, packet_has_identity
    notes: list[str] = []
    out = dict(residual)
    if packet is None or not packet_has_identity(packet):
        return out, notes
    for key in PACKET_IDENTITY_FIELDS:
        if key not in out:
            out[key] = packet.get(key)
            notes.append(f"copied residual.{key} from packet")
    if (
        previous_packet_hash
        and out.get("packet_hash") == previous_packet_hash
        and packet.get("packet_hash") != previous_packet_hash
    ):
        out["packet_hash"] = packet.get("packet_hash")
        notes.append("updated residual.packet_hash after packet migration")
    return out, notes


def print_migration_catalog() -> None:
    print("migrations  (versioned; removable only with a documented path)")
    for item in MIGRATION_CATALOG:
        print(
            f"  {item['id']:28} {item['kind']:14} "
            f"{item['from']} -> {item['to']}"
        )
        print(f"    {item['description']}")
    print("protocol keys (frozen)")
    print(f"  workspace.{PROTOCOL_WRITABLE_KEY}")
    print(f"  {PROTOCOL_SLAVE_MD}")


def plan_field_migrations(root: Path) -> list[dict[str, Any]]:
    """Collect versioned rewrite plans. Does not write."""
    actions: list[dict[str, Any]] = []
    stub_action = RootStub.plan(root)
    if stub_action:
        actions.append(stub_action)
    order_file = order_path(root)
    raw_order = _read_json_object(order_file)
    migrated_order: dict[str, Any] | None = None
    if isinstance(raw_order, dict):
        workspace = raw_order.get("workspace")
        new_ws, notes = normalize_workspace(workspace)
        updated = dict(raw_order)
        if notes:
            updated["workspace"] = new_ws
        updated, retired = strip_retired_runtime_keys(updated)
        migrated_order = updated
        notes = list(notes) + list(retired)
        if notes:
            actions.append(
                {
                    "id": "retired-runtime-keys" if retired else "protocol-writable-key",
                    "kind": "order",
                    "path": order_file,
                    "data": updated,
                    "notes": notes,
                }
            )
    state_file = state_path(root)
    raw_state = _read_json_object(state_file)
    if isinstance(raw_state, dict):
        updated, notes = migrate_state_artifact(raw_state)
        if notes:
            mid = (
                "retired-runtime-keys"
                if any("last_regime" in n or "across" in n for n in notes)
                and not any(n.startswith("filled state.") for n in notes)
                else "pre-0.4.2-state-defaults"
            )
            actions.append(
                {
                    "id": mid,
                    "kind": "state",
                    "path": state_file,
                    "data": updated,
                    "notes": notes,
                }
            )
    waves = field_home(root) / "waves"
    if not waves.is_dir():
        return actions
    for wave_path in sorted(p for p in waves.iterdir() if p.is_dir()):
        wave_num = int(wave_path.name) if wave_path.name.isdigit() else None
        packets_dir = wave_path / "packets"
        packet_by_child: dict[str, dict[str, Any]] = {}
        old_hash_by_child: dict[str, str] = {}
        raw_packets: list[dict[str, Any]] = []
        migrated_packets: list[dict[str, Any]] = []
        if packets_dir.is_dir():
            for path in sorted(packets_dir.glob("*.json")):
                raw = _read_json_object(path)
                if not isinstance(raw, dict):
                    continue
                raw_packets.append(raw)
                updated, notes = migrate_packet_artifact(raw)
                migrated_packets.append(updated)
                child_id = str(updated.get("child_id") or path.stem)
                packet_by_child[child_id] = updated
                old_hash = raw.get("packet_hash")
                new_hash = updated.get("packet_hash")
                if isinstance(old_hash, str) and isinstance(new_hash, str) and old_hash != new_hash:
                    old_hash_by_child[child_id] = old_hash
                if notes:
                    if all("workspace." in n for n in notes):
                        mid = "protocol-writable-key"
                    elif any(
                        "packet_id" in n or "order_id" in n or "packed_at" in n
                        or n == "computed packet_hash"
                        for n in notes
                    ):
                        mid = "pre-0.4.2-packet-identity"
                    else:
                        mid = "retired-runtime-keys"
                    actions.append(
                        {
                            "id": mid,
                            "kind": "packet",
                            "path": path,
                            "data": updated,
                            "notes": notes,
                        }
                    )
        residuals_dir = wave_path / "residuals"
        raw_residuals: dict[str, Any] = {}
        migrated_residuals: dict[str, Any] = {}
        if residuals_dir.is_dir():
            for path in sorted(residuals_dir.glob("*.json")):
                raw = _read_json_object(path)
                if not isinstance(raw, dict):
                    continue
                child_id = str(raw.get("child_id") or path.stem)
                raw_residuals[child_id] = raw
                packet = packet_by_child.get(child_id)
                updated, notes = migrate_residual_artifact(
                    raw,
                    packet,
                    previous_packet_hash=old_hash_by_child.get(child_id),
                )
                migrated_residuals[child_id] = updated
                if notes:
                    mid = (
                        "retired-runtime-keys"
                        if notes == ["updated residual.packet_hash after packet migration"]
                        else "pre-0.4.2-packet-identity"
                    )
                    actions.append(
                        {
                            "id": mid,
                            "kind": "residual",
                            "path": path,
                            "data": updated,
                            "notes": notes,
                        }
                    )
        prompts_dir = wave_path / "prompts"
        if prompts_dir.is_dir() and old_hash_by_child:
            for path in sorted(prompts_dir.glob("*.RESIDUAL.template.json")):
                raw = _read_json_object(path)
                if not isinstance(raw, dict):
                    continue
                child_id = str(
                    raw.get("child_id")
                    or path.name.removesuffix(".RESIDUAL.template.json")
                )
                old_hash = old_hash_by_child.get(child_id)
                packet = packet_by_child.get(child_id)
                if (
                    old_hash
                    and packet
                    and raw.get("packet_hash") == old_hash
                    and packet.get("packet_hash") != old_hash
                ):
                    updated = dict(raw)
                    updated["packet_hash"] = packet["packet_hash"]
                    actions.append(
                        {
                            "id": "retired-runtime-keys",
                            "kind": "residual-template",
                            "path": path,
                            "data": updated,
                            "notes": [
                                "updated residual template packet_hash after packet migration"
                            ],
                        }
                    )

        def _rehash_report_integration(
            doc: dict[str, Any], report_notes: list[str]
        ) -> tuple[dict[str, Any], list[str], str | None, str | None]:
            if (
                not old_hash_by_child
                or wave_num is None
                or migrated_order is None
                or not isinstance(doc.get("integration"), dict)
                or not doc["integration"].get("input_hash")
            ):
                return doc, report_notes, None, None
            from of.regime import integration_input_digest

            integration = doc["integration"]
            partial = bool(integration.get("partial"))
            apply_flag = bool(integration.get("apply"))
            old_digest = integration_input_digest(
                root,
                wave_num,
                raw_packets,
                partial=partial,
                apply=apply_flag,
                order=migrated_order,
                packet_hashes=old_hash_by_child,
                residuals_override=raw_residuals,
            )
            if integration.get("input_hash") != old_digest:
                return doc, report_notes, None, None
            new_digest = integration_input_digest(
                root,
                wave_num,
                migrated_packets,
                partial=partial,
                apply=apply_flag,
                order=migrated_order,
                residuals_override=migrated_residuals,
            )
            if new_digest == old_digest:
                return doc, report_notes, None, None
            out_doc = dict(doc)
            out_int = dict(integration)
            out_int["input_hash"] = new_digest
            rec_path = out_int.get("record_path")
            if isinstance(rec_path, str) and rec_path.endswith(f"/{old_digest}.json"):
                out_int["record_path"] = (
                    rec_path[: -len(f"{old_digest}.json")] + f"{new_digest}.json"
                )
            out_doc["integration"] = out_int
            return (
                out_doc,
                [*report_notes, "recomputed report integration.input_hash after packet migration"],
                old_digest,
                new_digest,
            )

        report_path = wave_path / "report.json"
        raw_report = _read_json_object(report_path)
        if isinstance(raw_report, dict):
            updated, notes = migrate_wave_report_artifact(raw_report)
            updated, notes, _old_d, _new_d = _rehash_report_integration(updated, notes)
            structural = updated != raw_report
            if notes and (structural or "integration" not in raw_report):
                actions.append(
                    {
                        "id": (
                            "retired-runtime-keys"
                            if structural
                            else "pre-0.4.2-report-readable"
                        ),
                        "kind": "wave-report",
                        "path": report_path,
                        "data": updated,
                        "notes": notes,
                        "write": structural,
                    }
                )
        integrations_dir = wave_path / "integrations"
        if integrations_dir.is_dir():
            for path in sorted(integrations_dir.glob("*.json")):
                if path.name == "observations.json":
                    continue
                raw_int = _read_json_object(path)
                if not isinstance(raw_int, dict):
                    continue
                updated, notes = migrate_wave_report_artifact(raw_int)
                updated, notes, old_d, new_d = _rehash_report_integration(updated, notes)
                structural = updated != raw_int
                if structural:
                    dest_path = (
                        integrations_dir / f"{new_d}.json"
                        if old_d and new_d and path.stem == old_d
                        else path
                    )
                    actions.append(
                        {
                            "id": "retired-runtime-keys",
                            "kind": "wave-report",
                            "path": dest_path,
                            "data": updated,
                            "notes": notes,
                            "write": True,
                        }
                    )
    return actions


def print_migration_plan(actions: list[dict[str, Any]]) -> None:
    if not actions:
        print("migrate      nothing to apply")
        return
    for item in actions:
        rel = item["path"].as_posix()
        print(f"{item['id']}  {item['kind']}  {rel}")
        for note in item["notes"]:
            print(f"  {note}")


def apply_field_migrations(actions: list[dict[str, Any]]) -> None:
    from of.pack import validate_packet, validate_residual
    for item in actions:
        if item.get("write", True) is False:
            continue
        kind = item["kind"]
        if kind == "root-stub":
            RootStub.apply(item)
            continue
        data = item["data"]
        if kind == "order":
            require_public_schema(data, "order.schema.json", "ORDER")
        elif kind == "state":
            require_public_schema(data, "state.schema.json", "state")
        elif kind == "packet":
            errs = validate_packet(data)
            if errs:
                die(f"invalid migrated packet {item['path']}:\n  " + "\n  ".join(errs))
        elif kind == "residual":
            errs = validate_residual(data)
            if errs:
                die(
                    f"invalid migrated residual {item['path']}:\n  "
                    + "\n  ".join(errs)
                )
        elif kind == "wave-report":
            require_public_schema(data, "wave-report.schema.json", "wave report")
        dump_json(item["path"], data)
