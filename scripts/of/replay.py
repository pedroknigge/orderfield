"""Discovery history as a replay world. Printed next is the policy.

A collected residual is a revealed node. Uncollected packets stay hidden
(prefix-only). The coding agent is unchanged. No new verb.

A requirement is green only when its residual is done and cites artifact_sha.
Red means owned and not green. The printed next stays on that red with the
same child. A different id is opened only after the current check is green,
or after the same id stays red for two waves — and that red still blocks
contrast. Stop only when every requirement is green.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Contract surfaces first. A plateau on CLI should open health/timeout/…,
# not another tweak of the same prefix.
_SURFACE_RANK = (
    "HEALTH",
    "TIMEOUT",
    "VERSION",
    "IDEMP",
    "HTTP",
    "WEBHOOK",
    "CLI",
)
_COST = 0.05
_PARALLEL = 0.1


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


def _prefix(req_id: str) -> str:
    return str(req_id).split("-", 1)[0].upper()


def _rank(req_id: str) -> tuple[int, str]:
    prefix = _prefix(req_id)
    try:
        index = _SURFACE_RANK.index(prefix)
    except ValueError:
        index = len(_SURFACE_RANK)
    return (index, req_id)


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
    def _touch(waves: list[dict[str, Any]]) -> tuple[set[str], dict[str, dict[str, Any]]]:
        green: set[str] = set()
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
                    if float(child["q"]) >= 1.0:
                        green.add(rid)
        return green, last

    @staticmethod
    def _red_streak(waves: list[dict[str, Any]], rid: str) -> int:
        streak = 0
        for wave in reversed(waves):
            touched = [child for child in wave["children"] if rid in child["reqs"]]
            if not touched:
                break
            if any(float(child["q"]) >= 1.0 for child in touched):
                break
            streak += 1
        return streak

    @staticmethod
    def decide(root: Path) -> dict[str, str] | None:
        if not DiscoveryReplay._active_ids(root):
            return None
        waves = DiscoveryReplay.waves(root)
        green, last = DiscoveryReplay._touch(waves)
        unowned = sorted(DiscoveryReplay._unowned(root), key=_rank)
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
            streak = DiscoveryReplay._red_streak(waves, rid)
            if streak >= 2 and unowned:
                opened = unowned[0]
                return {
                    "label": "OPEN",
                    "detail": (
                        f"{rid} still red after {streak} waves; do not contrast. "
                        + pack(role="explorer", child_id=opened, rid=opened)
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
            done = ", ".join(sorted(green)) or "none"
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
