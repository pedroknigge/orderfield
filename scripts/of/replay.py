"""Discovery history as a replay world. Printed next is the policy.

A collected residual is a revealed node. Uncollected packets stay hidden
(prefix-only). The coding agent is unchanged. No new verb.

Replay score, same shape as Dream-RSI: best quality, minus attempts, plus
a parallelism bonus for disjoint owns-path in that wave. A later wave that
does not beat the previous one is a plateau: do not print a bare next-wave.
Open a different unowned requirement, or stop and contrast.
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
            qualities = [_quality(res) for _pkt, res in revealed]
            paths = {
                p
                for pkt, _res in revealed
                for p in packet_owns_paths(pkt)
                if p
            }
            reqs = sorted(
                {
                    str(rid)
                    for pkt, _res in revealed
                    for rid in (pkt.get("owns_requirements") or [])
                    if str(rid).strip()
                }
            )
            n = len(revealed)
            parallel = (len(paths) / n) if n else 0.0
            found.append(
                {
                    "wave": wave,
                    "n": n,
                    "best": max(qualities),
                    "V": max(qualities) - _COST * n + _PARALLEL * parallel,
                    "reqs": reqs,
                    "prefixes": sorted({_prefix(r) for r in reqs}),
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
    def decide(root: Path) -> dict[str, str] | None:
        waves = DiscoveryReplay.waves(root)
        if len(waves) < 2:
            return None
        prev, last = waves[-2], waves[-1]
        if float(last["V"]) > float(prev["V"]):
            return None
        # A larger wave costs more. Quality that held is not a plateau.
        if float(last["best"]) + 1e-9 >= float(prev["best"]) and float(last["best"]) >= 0.55:
            return None
        same = bool(set(last["reqs"]) & set(prev["reqs"]))
        if abs(float(last["V"]) - float(prev["V"])) < 1e-9 and not same:
            return None
        saturated = ", ".join(last["reqs"]) or "(none)"
        unowned = DiscoveryReplay._unowned(root)
        opened = [rid for rid in unowned if rid not in set(last["reqs"])]
        opened.sort(key=_rank)
        score = (
            f"replay V {float(prev['V']):.2f} -> {float(last['V']):.2f} "
            f"on {saturated}"
        )
        if not opened:
            return {
                "label": "STOP",
                "detail": (
                    f"{score}; plateau and nothing unowned. "
                    "of contrast. do not pack another refine"
                ),
            }
        rid = opened[0]
        slug = rid.replace("-", "_").lower()
        return {
            "label": "OPEN",
            "detail": (
                f"{score}; do not refine. "
                f"of next-wave && of pack --role implementer --child-id {rid} "
                f"--owns-requirement {rid} --owns-path src/{slug}.py "
                f"--slice 'cover {rid}'"
            ),
        }

    @staticmethod
    def lines(root: Path) -> list[str] | None:
        decision = DiscoveryReplay.decide(root)
        if not decision:
            return None
        return [decision["label"], decision["detail"]]
