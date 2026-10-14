"""One-pass doctor diagnostics (`DoctorSkew`).

Extracted from `of.field` so read-path doctor composition stays modular
while `from of.field import DoctorSkew` remains unchanged.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from of.field import (
    ActiveField,
    PackedAge,
    RootStub,
    SkillVersionSkew,
    SpawnRecord,
    _read_json_object,
    child_pulse_age,
    field_home,
    field_is_open,
    field_rel,
    fmt_age,
    list_field_homes,
    load_state,
    load_worktrees,
    of_dir,
)


class DoctorSkew:
    """One-pass doctor: skill VERSION, ACTIVE pointer, stale packs.

    Reuses SkillVersionSkew, ActiveField, list_field_homes, field_is_open,
    PackedAge, RootStub, and packet_is_stale. Read-path only. No new
    schema. No new CLI flag.

    Skill VERSION mismatch is advisory (WARN / exit 0). Closed-field
    historical pack skew (retained order_rev / packed_age vs the final
    ORDER) is informational — not FAIL. Two or more sibling homes open
    without CLOSE.json are hygiene WARN (not FAIL). Open-field, schema,
    lock, symlink, ACTIVE/stub (leftover root ORDER.json needs
    ``of migrate``), and kernel failures still FAIL (exit 2).

    Version skew already lived on doctor (0.7.10). ACTIVE pointer and
    packed-age lived on fields/status/resume. Closed vs open already
    lived on FieldRoster. This class is the compose step, not a
    second ledger. Pack lines name field id + wave.
    """

    HISTORICAL_NOTE = (
        "closed-field historical packs are informational (not field FAIL)"
    )
    OPEN_NOTE = (
        "sibling fields without CLOSE are hygiene "
        "(not field FAIL; of fields; "
        "of close --abandoned --reason TEXT; "
        "of gc --archive-field after close)"
    )

    @staticmethod
    def skills(
        home: Path | None = None, expected: str | None = None
    ) -> tuple[list[str], bool]:
        return SkillVersionSkew.report(home=home, expected=expected)

    @staticmethod
    def inspect_home(root: Path) -> Path | None:
        """ACTIVE match, else unique nested/legacy home. Does not write."""
        homes = list_field_homes(root)
        if not homes:
            return None
        pointed = ActiveField.read(root)
        if pointed:
            for fid, home, _order in homes:
                if fid == pointed:
                    return home
        of = of_dir(root)
        nested = [home for _fid, home, _order in homes if home != of]
        candidates = nested if nested else [home for _fid, home, _order in homes]
        if len(candidates) == 1:
            return candidates[0]
        return None

    @staticmethod
    def leftover_stub(root: Path) -> Path | None:
        return RootStub.leftover_path(root)

    @staticmethod
    def wave_packet_files(
        home: Path,
    ) -> tuple[int, list[tuple[Path, dict[str, Any]]]]:
        state = _read_json_object(home / "state.json") or {}
        try:
            wave = int(state.get("wave") or 1)
        except (TypeError, ValueError):
            wave = 1
        pdir = home / f"waves/{wave:03d}/packets"
        files: list[tuple[Path, dict[str, Any]]] = []
        if pdir.is_dir():
            try:
                paths = sorted(pdir.glob("*.json"))
            except OSError:
                paths = []
            for path in paths:
                data = _read_json_object(path)
                if isinstance(data, dict):
                    files.append((path, data))
        return wave, files

    @staticmethod
    def wave_packets(home: Path) -> tuple[int, list[dict[str, Any]]]:
        wave, files = DoctorSkew.wave_packet_files(home)
        return wave, [data for _path, data in files]

    @staticmethod
    def residual_missing(home: Path, packet: dict[str, Any], wave: int) -> bool:
        rel = str(packet.get("residual_path") or "").strip()
        cid = str(packet.get("child_id") or "").strip()
        name = Path(rel).name if rel else (f"{cid}.json" if cid else "")
        if not name:
            return True
        return not (home / f"waves/{int(wave):03d}/residuals" / name).is_file()

    @staticmethod
    def home_closed(home: Path, order: dict[str, Any]) -> bool:
        """spec_closed (of fields) or retained CLOSE.json. Do not rewrite."""
        if not field_is_open(order):
            return True
        proof = home / "CLOSE.json"
        return proof.is_file() and not proof.is_symlink()

    @staticmethod
    def pack_diag(fid: str, wave: int, body: str) -> str:
        return f"  packs         {fid} wave {wave}  {body}"

    @staticmethod
    def active(root: Path) -> tuple[list[str], bool]:
        homes = list_field_homes(root)
        pointed = ActiveField.read(root)
        pointer_file = ActiveField.path(root)
        ids = {fid for fid, _home, _order in homes}
        lines: list[str] = []
        skewed = False
        if not homes:
            lines.append("  active        -  (no fields)")
        elif pointed and pointed in ids:
            pointed_closed = False
            for fid, home, order in homes:
                if fid == pointed:
                    pointed_closed = DoctorSkew.home_closed(home, order)
                    break
            if pointed_closed:
                lines.append(f"  active        {pointed}  closed")
            else:
                lines.append(f"  active        {pointed}  ok")
        elif pointed:
            lines.append(f"  active        {pointed}  SKEW  (no home)")
            skewed = True
        elif pointer_file.is_file():
            lines.append("  active        -  SKEW  (invalid pointer)")
            skewed = True
        elif len(homes) > 1:
            if all(DoctorSkew.home_closed(home, order) for _fid, home, order in homes):
                lines.append("  active        -  closed")
            else:
                lines.append("  active        -  SKEW  (missing pointer)")
                skewed = True
        else:
            fid, home, order = homes[0]
            if DoctorSkew.home_closed(home, order):
                lines.append(f"  active        {fid}  closed")
            else:
                lines.append(f"  active        {fid}  ok")
        stub = DoctorSkew.leftover_stub(root)
        if stub is not None:
            rel = field_rel(root, stub)
            lines.append(
                f"  stub          {rel}  SKEW  "
                f"({RootStub.migrate_hint(root)})"
            )
            lines.append(
                f"  migrate       required  {rel}  SKEW  "
                f"({RootStub.migrate_hint(root)}; not a silent delete)"
            )
            skewed = True
        else:
            lines.append("  stub          none")
        return lines, skewed

    @staticmethod
    def open_without_close(root: Path) -> list[tuple[str, Path]]:
        """Live homes that are still open and have no CLOSE.json."""
        rows: list[tuple[str, Path]] = []
        for fid, home, order in list_field_homes(root):
            if field_is_open(order) and not (home / "CLOSE.json").is_file():
                rows.append((fid, home))
        return rows

    @staticmethod
    def open_siblings(root: Path) -> tuple[list[str], bool]:
        """Two or more open homes without CLOSE. Advisory; not FAIL."""
        rows = DoctorSkew.open_without_close(root)
        if len(rows) < 2:
            return [], False
        ids = [fid for fid, _home in rows]
        shown = ", ".join(ids[:8])
        extra = f" +{len(ids) - 8}" if len(ids) > 8 else ""
        return [
            f"  open          {len(rows)} fields  no CLOSE  "
            f"({shown}{extra}; of fields)",
            f"  note          {DoctorSkew.OPEN_NOTE}",
        ], True

    @staticmethod
    def packs(
        root: Path, *, now: float | None = None
    ) -> tuple[list[str], bool]:
        from of.pack import packet_is_stale

        homes = list_field_homes(root)
        if not homes:
            return ["  packs         none"], False
        lines: list[str] = []
        skewed = False
        historical = False
        for fid, home, order in homes:
            closed = DoctorSkew.home_closed(home, order)
            wave, packets = DoctorSkew.wave_packets(home)
            flying = [
                pkt
                for pkt in packets
                if DoctorSkew.residual_missing(home, pkt, wave)
            ]
            overdue = PackedAge.overdue(flying, now=now)
            if overdue:
                parts = "; ".join(f"{cid} {fmt_age(age)}" for cid, age in overdue)
                if closed:
                    lines.append(
                        DoctorSkew.pack_diag(
                            fid,
                            wave,
                            f"{PackedAge.LABEL}  {parts}  (historical; closed)",
                        )
                    )
                    historical = True
                else:
                    lines.append(
                        DoctorSkew.pack_diag(
                            fid,
                            wave,
                            f"{PackedAge.LABEL}  {parts}  "
                            f"(past {PackedAge.SLA_LABEL} SLA)",
                        )
                    )
                    skewed = True
            for pkt in packets:
                stale = packet_is_stale(pkt, order)
                rev_only = (
                    closed
                    and not stale
                    and pkt.get("order_rev") != order.get("rev")
                )
                if not stale and not rev_only:
                    continue
                cid = str(pkt.get("child_id") or "?")
                if closed:
                    lines.append(
                        DoctorSkew.pack_diag(
                            fid,
                            wave,
                            f"{cid}  historical  (order_rev; closed)",
                        )
                    )
                    historical = True
                else:
                    lines.append(
                        DoctorSkew.pack_diag(
                            fid, wave, f"{cid}  stale  (order_rev)"
                        )
                    )
                    skewed = True
        if historical:
            lines.append(f"  note          {DoctorSkew.HISTORICAL_NOTE}")
        if not lines:
            return ["  packs         none"], False
        return lines, skewed

    @staticmethod
    def recorded_worktrees(root: Path) -> list[str]:
        trees = load_worktrees(root).get("trees") or {}
        return sorted(str(cid) for cid in trees if str(cid).strip())

    @staticmethod
    def orphaned_worktrees(root: Path) -> list[str]:
        """Recorded of-worktrees whose children are settled or gone.

        Flying children (started-only spawn or residual MISSING) keep a
        recorded tree on purpose. Advisory; not a host process poll.
        """
        ids = DoctorSkew.recorded_worktrees(root)
        if not ids:
            return []
        _wave, packets = DoctorSkew.wave_packets(field_home(root))
        by_id = {
            str(pkt.get("child_id") or "").strip(): pkt
            for pkt in packets
            if str(pkt.get("child_id") or "").strip()
        }
        orphaned: list[str] = []
        for cid in ids:
            pkt = by_id.get(cid)
            if pkt is None or not SpawnRecord.flying(root, pkt):
                orphaned.append(cid)
        return orphaned

    @staticmethod
    def worktrees(root: Path) -> tuple[list[str], bool]:
        """Orphaned of-worktree records vs settled children. Advisory."""
        ids = DoctorSkew.orphaned_worktrees(root)
        if not ids:
            return [], False
        shown = ", ".join(ids[:8])
        extra = f" +{len(ids) - 8}" if len(ids) > 8 else ""
        return [
            f"  worktrees     {len(ids)} orphaned  "
            f"({shown}{extra}; of worktree remove --child-id <id>)",
            "  note          leftover of-worktrees after settle are advisory "
            "(not field FAIL; not a process manager; not a host poll)",
        ], True

    OVER_NOTE = (
        "over-budget open spawn is advisory "
        "(not a supervisor; kernel does not kill)"
    )

    @staticmethod
    def over_budget(
        root: Path, *, now: float | None = None
    ) -> tuple[list[str], bool]:
        """Open spawn past budget.seconds, or live + idle past pulse-stale.
        Advisory; not FAIL."""
        from of.pack import packed_children

        try:
            state = load_state(root)
            wave = int(state.get("wave") or 1)
        except (OSError, SystemExit, TypeError, ValueError):
            return [], False
        packets = packed_children(root, wave)
        lines: list[str] = []
        clock = now if now is not None else time.time()
        for pkt in packets:
            row = SpawnRecord.over_budget(
                SpawnRecord.load(root, pkt),
                pkt,
                now=clock,
                age_s=child_pulse_age(root, pkt, clock),
            )
            if row is None:
                continue
            pid = row.get("pid")
            pid_s = "none" if pid is None else str(pid)
            age = fmt_age(float(row.get("age_s") or 0))
            lines.append(
                f"  spawn         {row['child_id']}  {SpawnRecord.OVER_BUDGET}  "
                f"{row['kind']}  pid={pid_s}  started {age} ago "
                f"budget={row['budget_s']}s"
            )
        if not lines:
            return [], False
        lines.append(f"  note          {DoctorSkew.OVER_NOTE}")
        return lines, True

    @staticmethod
    def emit_teardown(
        root: Path, child_ids: list[str] | None = None
    ) -> bool:
        """Print of-worktree remove next after collect/abandon/close.

        Teaching only. Does not remove trees, poll a host, or kill panes.
        """
        recorded = set(DoctorSkew.recorded_worktrees(root))
        if child_ids is None:
            ids = DoctorSkew.orphaned_worktrees(root)
        else:
            ids = [
                cid
                for cid in child_ids
                if str(cid).strip() and str(cid).strip() in recorded
            ]
        if not ids:
            return False
        for cid in ids:
            print(f"next         of worktree remove --child-id {cid}")
        print(
            "note         leftover of-worktree after settle; "
            "worker-stop does not delete it or Host panes; "
            "Orca Host: orca worktree rm --worktree id:<repo>::<path> "
            "--force (not a supervisor)"
        )
        return True

    @staticmethod
    def field(
        root: Path, *, now: float | None = None
    ) -> tuple[list[str], bool]:
        active_lines, active_skew = DoctorSkew.active(root)
        pack_lines, pack_skew = DoctorSkew.packs(root, now=now)
        open_lines, _open_warn = DoctorSkew.open_siblings(root)
        return (
            active_lines + pack_lines + open_lines,
            active_skew or pack_skew,
        )
