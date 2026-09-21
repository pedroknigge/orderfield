"""Discovery history as a replay world. Printed next is the policy.

A collected residual is a revealed node. Uncollected packets stay hidden
(prefix-only). The coding agent is unchanged. No new verb.

The order parameter is one red check. Green is an external check file the
leader writes (`.orderfield/checks/<id>.json`), not a child `artifact_sha`.
While any touched requirement lacks that file, the printed next stays on the
latest red with the same child. Two waves on that red escalate. A different
id opens only when nothing touched is red, and then only the next unowned
id in specification order. Stop only when every active requirement is green.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_COST = 0.05
_PARALLEL = 0.1
_CHECK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def _quality(residual: dict[str, Any]) -> float:
    status = str(residual.get("status") or "")
    inner = residual.get("residual")
    evidence = str(inner.get("evidence") or "") if isinstance(inner, dict) else ""
    cited = "artifact_sha:" in evidence
    if status == "done" and cited:
        return 1.0
    if status == "done":
        return 0.55
    if status == "blocked":
        return 0.2
    if status == "threshold":
        return 0.0
    return 0.1


class DiscoveryReplay:
    """Offline policy over collected waves. None means the legal next stands."""

    @staticmethod
    def waves(root: Path) -> list[dict[str, Any]]:
        from of.field import load_state
        from of.pack import packet_owns_paths, packed_children, try_load_packet_residual

        state = load_state(root)
        last = int(state.get("wave") or 1)
        found: list[dict[str, Any]] = []
        for wave in range(1, last + 1):
            revealed: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for packet in packed_children(root, wave):
                residual = try_load_packet_residual(root, packet)
                if isinstance(residual, dict):
                    revealed.append((packet, residual))
            if not revealed:
                continue
            children: list[dict[str, Any]] = []
            for pkt, res in revealed:
                reqs = sorted(
                    {
                        str(rid)
                        for rid in (pkt.get("owns_requirements") or [])
                        if str(rid).strip()
                    }
                )
                children.append(
                    {
                        "child_id": str(pkt.get("child_id") or ""),
                        "role": str(pkt.get("role") or "explorer"),
                        "paths": [p for p in packet_owns_paths(pkt) if p],
                        "reqs": reqs,
                        "q": _quality(res),
                    }
                )
            qualities = [child["q"] for child in children]
            paths = {p for child in children for p in child["paths"]}
            reqs = sorted({rid for child in children for rid in child["reqs"]})
            n = len(revealed)
            parallel = (len(paths) / n) if n else 0.0
            found.append(
                {
                    "wave": wave,
                    "n": n,
                    "best": max(qualities),
                    "V": max(qualities) - _COST * n + _PARALLEL * parallel,
                    "reqs": reqs,
                    "children": children,
                }
            )
        return found

    @staticmethod
    def _unowned(root: Path) -> list[str]:
        from of.spec import is_active_requirement, load_requirements

        ids: list[str] = []
        for item in load_requirements(root).get("requirements") or []:
            if not isinstance(item, dict) or not is_active_requirement(item):
                continue
            if item.get("owned_by"):
                continue
            if str(item.get("status") or "unowned") != "unowned":
                continue
            rid = str(item.get("id") or "").strip()
            if rid:
                ids.append(rid)
        return ids

    @staticmethod
    def _active_ids(root: Path) -> list[str]:
        from of.spec import is_active_requirement, load_requirements

        ids: list[str] = []
        for item in load_requirements(root).get("requirements") or []:
            if not isinstance(item, dict) or not is_active_requirement(item):
                continue
            rid = str(item.get("id") or "").strip()
            if rid:
                ids.append(rid)
        return ids

    @staticmethod
    def _command(
        root: Path,
        waves: list[dict[str, Any]],
        *,
        role: str,
        child_id: str,
        rid: str,
        paths: list[str],
    ) -> str:
        import shlex

        from of.field import load_state

        args = [
            "--role",
            role or "explorer",
            "--child-id",
            child_id,
            "--owns-requirement",
            rid,
        ]
        for path in paths:
            args.extend(["--owns-path", path])
        args.extend(["--slice", f"cover {rid}"])
        pack = "of pack " + shlex.join(args)
        if not waves:
            return pack
        state = load_state(root)
        if int(state.get("wave") or 1) == int(waves[-1]["wave"]):
            return "of next-wave && " + pack
        return pack

    @staticmethod
    def check_path(root: Path, rid: str) -> Path:
        return root / ".orderfield" / "checks" / f"{rid}.json"

    @staticmethod
    def externally_green(root: Path, rid: str) -> bool:
        if not _CHECK_ID.fullmatch(rid):
            return False
        path = DiscoveryReplay.check_path(root, rid)
        if not path.is_file():
            return False
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(doc, dict) or doc.get("pass") is not True:
            return False
        named = str(doc.get("id") or "").strip()
        return named == rid

    @staticmethod
    def _green(root: Path) -> set[str]:
        return {
            rid
            for rid in DiscoveryReplay._active_ids(root)
            if DiscoveryReplay.externally_green(root, rid)
        }

    @staticmethod
    def _last(waves: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        last: dict[str, dict[str, Any]] = {}
        for wave in waves:
            for child in wave["children"]:
                for rid in child["reqs"]:
                    last[rid] = {
                        "child_id": child["child_id"],
                        "role": child["role"],
                        "paths": list(child["paths"]),
                        "q": child["q"],
                        "wave": wave["wave"],
                    }
        return last

    @staticmethod
    def _red_streak(
        waves: list[dict[str, Any]], rid: str, *, green: set[str]
    ) -> int:
        if rid in green:
            return 0
        streak = 0
        for wave in reversed(waves):
            touched = [child for child in wave["children"] if rid in child["reqs"]]
            if not touched:
                break
            streak += 1
        return streak

    @staticmethod
    def _escalated(root: Path, rid: str, wave: int) -> bool:
        """True when this red wave already became escalate_up.

        A later printed next, after the leader patches, retries the same
        child. It does not open a sibling, and it does not escalate again
        until a newer wave is also red.
        """
        from of.field import wave_dir

        path = wave_dir(int(wave), root) / "report.json"
        if not path.is_file():
            return False
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(report, dict):
            return False
        return report.get("regime") == "escalate_up" and rid in str(
            report.get("reason") or ""
        )

    @staticmethod
    def unstable(root: Path) -> str | None:
        """Requirement id that stayed red for two waves, or None.

        Integrate turns this into escalate_up. A sibling pack is not the
        regime change.
        """
        if not DiscoveryReplay._active_ids(root):
            return None
        waves = DiscoveryReplay.waves(root)
        green = DiscoveryReplay._green(root)
        last = DiscoveryReplay._last(waves)
        reds = [rid for rid in last if rid not in green]
        reds.sort(key=lambda rid: int(last[rid]["wave"]), reverse=True)
        for rid in reds:
            if DiscoveryReplay._red_streak(waves, rid, green=green) >= 2:
                return rid
        return None

    @staticmethod
    def decide(root: Path) -> dict[str, str] | None:
        if not DiscoveryReplay._active_ids(root):
            return None
        waves = DiscoveryReplay.waves(root)
        green = DiscoveryReplay._green(root)
        last = DiscoveryReplay._last(waves)
        unowned = [
            rid for rid in DiscoveryReplay._unowned(root) if rid not in green
        ]
        reds = [rid for rid in last if rid not in green]
        reds.sort(key=lambda rid: int(last[rid]["wave"]), reverse=True)

        def pack(
            *,
            role: str,
            child_id: str,
            rid: str,
            paths: list[str] | None = None,
        ) -> str:
            return DiscoveryReplay._command(
                root,
                waves,
                role=role,
                child_id=child_id,
                rid=rid,
                paths=paths or [],
            )

        if reds:
            rid = reds[0]
            touch = last[rid]
            streak = DiscoveryReplay._red_streak(waves, rid, green=green)
            if streak >= 2 and not DiscoveryReplay._escalated(
                root, rid, int(touch["wave"])
            ):
                return {
                    "label": "ESCALATE",
                    "detail": (
                        f"{rid} did not relax after {streak} waves. "
                        "do not open another requirement. "
                        "of patch then of next-wave"
                    ),
                }
            return {
                "label": "CONTINUE",
                "detail": (
                    f"{rid} check red; same child. do not open another. "
                    + pack(
                        role=str(touch["role"]),
                        child_id=str(touch["child_id"]),
                        rid=rid,
                        paths=list(touch["paths"]),
                    )
                ),
            }
        if unowned:
            opened = unowned[0]
            named = [
                rid
                for rid in DiscoveryReplay._active_ids(root)
                if rid in green
            ]
            done = ", ".join(named) or "none"
            return {
                "label": "OPEN",
                "detail": (
                    f"{done} green; open next. "
                    + pack(role="explorer", child_id=opened, rid=opened)
                ),
            }
        if green:
            return {
                "label": "STOP",
                "detail": "all requirement checks green. of contrast. do not pack",
            }
        return None

    @staticmethod
    def lines(root: Path) -> list[str] | None:
        decision = DiscoveryReplay.decide(root)
        if not decision:
            return None
        return [decision["label"], decision["detail"]]
