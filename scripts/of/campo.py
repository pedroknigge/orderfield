"""Campo: written arena, peer election, pin of ORDER + leader.

Deep module. Init and pack call this interface. Ballot rules, plurality
math, tie-break, and the verbatim ORDER snapshot stay here.

Contestants and crew share the field cwd and git branch. A commit on that
branch is how the others catch up (proposals, ballots, code, residual
notes). This module does not create a worktree, does not run a merge-packet,
and does not accept a host-appointed leader. Two writers do not edit one
path at once.

Re-open after verifier refuse is parent epic #333, not this slice.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from of_adapters import AdapterDetect, AdapterHints, detect_adapters

from of.field import (
    die,
    dump_bytes,
    dump_json,
    field_home,
    field_is_file,
    field_read_bytes,
    field_read_text,
    load_order,
    order_path,
    sha256_text,
    skill_root,
    spec_path,
)

CONFIG_ENV = "OF_CONFIG"
_MODEL_BAD = re.compile(r"[\x00-\x1f\x7f]")
STANCES = frozenset({"concede", "challenge"})
RULE = "plurality-concede"
TIE_BREAK = "contestant-id"
PEERS = "equals; list order is not rank and not a role"


class Campo:
    """Public surface: config, enter, settle, hold_pack. Election stays inside."""

    @staticmethod
    def config_path() -> Path:
        override = (os.environ.get(CONFIG_ENV) or "").strip()
        if override:
            return Path(override)
        return Path.home() / ".orderfield" / "config.json"

    @staticmethod
    def read_config() -> dict[str, Any]:
        path = Campo.config_path()
        if not path.is_file() or path.is_symlink():
            return {"v": 1, "contestants": []}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            die(f"invalid campo config {path}: {exc}")
        if not isinstance(raw, dict):
            die(f"invalid campo config {path}: expected an object")
        if "contestants" not in raw and ("models" in raw or "effort" in raw):
            die(
                "campo config is a contestants list; "
                "rewrite with of config set --contestant MODEL EFFORT"
            )
        rows = raw.get("contestants") or []
        if not isinstance(rows, list):
            die(f"invalid campo config {path}: contestants must be a list")
        clean = [Campo._seat_from_disk(item, path) for item in rows]
        return {"v": 1, "contestants": clean}

    @staticmethod
    def write_defaults(seats: list[tuple[str, str]]) -> dict[str, Any]:
        clean = [Campo._normalize_seat(model, effort) for model, effort in seats]
        if len(clean) < 2:
            die("of config set needs at least two --contestant values")
        seen: set[str] = set()
        for seat in clean:
            if seat["model"] in seen:
                die(f"duplicate contestant {seat['model']}")
            seen.add(seat["model"])
        doc = {"v": 1, "contestants": clean}
        dump_json(Campo.config_path(), doc)
        return doc

    @staticmethod
    def contestants(doc: dict[str, Any] | None = None) -> list[dict[str, str]]:
        cfg = doc if doc is not None else Campo.read_config()
        rows: list[dict[str, str]] = []
        for index, seat in enumerate(cfg.get("contestants") or [], start=1):
            if not isinstance(seat, dict):
                continue
            rows.append(
                {
                    "id": f"c{index}",
                    "model": str(seat.get("model") or ""),
                    "effort": str(seat.get("effort") or ""),
                }
            )
        return rows

    @staticmethod
    def require_roster() -> list[dict[str, str]]:
        rows = Campo.contestants()
        if len(rows) < 2:
            die(
                "campo needs N>=2 contestants; "
                "of config set --contestant MODEL EFFORT"
            )
        return rows

    @staticmethod
    def installed() -> list[dict[str, str]]:
        """Catalog models whose harness CLI is on PATH. Not a login. Not a role."""
        inventory = AdapterDetect.inventory(detect_adapters())
        present = {
            str(row["name"]): str(row.get("path") or "")
            for row in inventory
            if row.get("status") == AdapterDetect.PRESENT
        }
        found: list[dict[str, str]] = []
        for row in Campo._catalog_rows():
            harness = str(row.get("harness") or "")
            if harness not in present:
                continue
            found.append(
                {
                    "harness": harness,
                    "model": str(row.get("model_id") or ""),
                    "path": present[harness],
                }
            )
        return found

    @staticmethod
    def audit_lines() -> list[str]:
        inventory = AdapterDetect.inventory(detect_adapters())
        by_harness: dict[str, list[str]] = {}
        for seat in Campo.installed():
            by_harness.setdefault(seat["harness"], []).append(seat["model"])
        lines = [
            "installed   harness CLIs on PATH; catalog models for those CLIs",
        ]
        for row in inventory:
            name = str(row["name"])
            lines.append(
                f"  {name:10} {row['status']:8} {row['path']}"
            )
            if row.get("status") != AdapterDetect.PRESENT:
                continue
            models = by_harness.get(name) or []
            lines.append(
                "             " + (" ".join(models) if models else "(no catalog model)")
            )
        lines.append(f"honesty     {AdapterDetect.HONESTY}")
        return lines

    @staticmethod
    def resolve_spawn(seat: dict[str, str]) -> dict[str, str]:
        """Bind one stored peer to the single installed harness that has it."""
        model = str(seat.get("model") or "")
        hits = Campo._installed_hits(model)
        if not hits:
            die(f"campo spawn refused: {model!r} is not installed")
        if len(hits) > 1:
            names = ", ".join(row["harness"] for row in hits)
            die(
                f"campo spawn refused: {model!r} is installed on more than one "
                f"harness ({names})"
            )
        return {
            "harness": hits[0]["harness"],
            "model": hits[0]["model"],
            "effort": Campo._effort(str(seat.get("effort") or "")),
        }

    @staticmethod
    def arena(root: Path) -> Path:
        return field_home(root) / "campo"

    @staticmethod
    def enter(
        root: Path,
        order: dict[str, Any],
        source_text: str | None = None,
    ) -> dict[str, Any]:
        """Open the arena and pin only when every peer ballot is already valid."""
        del source_text  # SPEC / PlanIngress already hold the verbatim brief
        Campo._open(root, order)
        return Campo.settle(root)

    @staticmethod
    def settle(root: Path) -> dict[str, Any]:
        """Elect from disk ballots. No leader argument. No worktree."""
        rnd = Campo._read_round(root)
        if rnd is None:
            die("campo is not open; of init --campo")
        if rnd.get("status") == "pinned" and Campo._leader_path(root).is_file():
            return Campo._pinned_doc(root, rnd)
        roster = Campo._roster_ids(rnd)
        ballots = Campo._ballots(root, roster)
        if ballots is None:
            return Campo._open_doc(
                root,
                "no pin without ballots",
            )
        blocked = Campo._fidelity_block(root, rnd)
        if blocked:
            return Campo._open_doc(root, blocked)
        elected = Campo._elect(roster, ballots)
        if elected is None:
            return Campo._open_doc(
                root,
                "no pin without a concede",
            )
        leader, tally = elected
        Campo._pin(root, rnd, leader, tally)
        pinned = Campo._read_round(root) or rnd
        return Campo._pinned_doc(root, pinned)

    @staticmethod
    def hold_pack(root: Path, role: str) -> str | None:
        """Implementer pack waits for a pinned leader. Other roles are unchanged."""
        if str(role) != "implementer":
            return None
        rnd = Campo._read_round(root)
        if rnd is None:
            return None
        if rnd.get("status") == "pinned" and Campo._leader_path(root).is_file():
            return None
        return (
            "of pack refused: campo has no pinned leader; "
            "peers ballot under campo/ballots then of campo settle. "
            "The host does not appoint the leader"
        )

    @staticmethod
    def speak(doc: dict[str, Any]) -> list[str]:
        if doc.get("pinned"):
            crew = ",".join(str(item) for item in (doc.get("crew") or []))
            return [
                f"campo        pinned  leader={doc.get('leader')}  crew={crew}",
                "orden        pack on this branch; the host does not appoint the leader",
            ]
        reason = str(doc.get("reason") or "ballots incomplete")
        return [
            f"campo        open  {reason}",
            "next         write campo/proposals/<id>.md and "
            "campo/ballots/<id>.json then of campo settle",
        ]

    @staticmethod
    def _model(raw: str) -> str:
        model = str(raw or "").strip()
        if (
            not model
            or len(model) > 128
            or _MODEL_BAD.search(model)
            or model[0] in "-."
        ):
            die(f"invalid contestant model {raw!r}")
        return model

    @staticmethod
    def _effort(raw: str) -> str:
        picked = str(raw or "").strip().casefold()
        if picked not in AdapterHints.EFFORTS:
            die(
                f"contestant effort must be {'|'.join(sorted(AdapterHints.EFFORTS))} "
                f"(got {raw!r})"
            )
        return picked

    @staticmethod
    def _fold(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(text).casefold())

    @staticmethod
    def _catalog_rows() -> list[dict[str, Any]]:
        from of.model_catalog import ModelCatalog

        path = ModelCatalog.json_path(skill_root())
        if not path.is_file():
            return []
        try:
            doc = ModelCatalog.load(skill_root())
        except (OSError, json.JSONDecodeError, ValueError):
            return []
        rows: list[dict[str, Any]] = []
        for row in ModelCatalog.models(doc):
            model_id = str(row.get("model_id") or "")
            harness = str(row.get("harness") or "")
            if not model_id or model_id == "(user-config)" or not harness:
                continue
            rows.append(row)
        return rows

    @staticmethod
    def _installed_hits(model: str) -> list[dict[str, str]]:
        folded = Campo._fold(model)
        hits: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in Campo.installed():
            if Campo._fold(row["model"]) != folded:
                continue
            if row["harness"] in seen:
                continue
            seen.add(row["harness"])
            hits.append(row)
        return hits

    @staticmethod
    def _normalize_seat(model: str, effort: str) -> dict[str, str]:
        picked_model = Campo._model(model)
        picked_effort = Campo._effort(effort)
        hits = Campo._installed_hits(picked_model)
        if not hits:
            die(
                f"{picked_model!r} is not installed; "
                "of config lists harness CLIs on PATH and their catalog models"
            )
        if len(hits) > 1:
            names = ", ".join(row["harness"] for row in hits)
            die(
                f"{picked_model!r} is installed on more than one harness ({names}); "
                "a contestant is model + effort, and this name is not one peer"
            )
        return {"model": hits[0]["model"], "effort": picked_effort}

    @staticmethod
    def _seat_from_disk(item: Any, path: Path) -> dict[str, str]:
        if not isinstance(item, dict):
            die(f"invalid campo config {path}: each contestant must be an object")
        return {
            "model": Campo._model(str(item.get("model") or "")),
            "effort": Campo._effort(str(item.get("effort") or "")),
        }

    @staticmethod
    def _open(root: Path, order: dict[str, Any]) -> None:
        roster = Campo.require_roster()
        arena = Campo.arena(root)
        (arena / "proposals").mkdir(parents=True, exist_ok=True)
        (arena / "ballots").mkdir(parents=True, exist_ok=True)
        from of.regime import PlanIngress

        pins = [
            {"rel": rel, "sha": digest}
            for rel, digest in PlanIngress.pinned(order)
        ]
        brief_text = Campo._text(spec_path(root))
        brief = sha256_text(brief_text) if brief_text is not None else ""
        dump_json(
            arena / "round.json",
            {
                "v": 1,
                "status": "open",
                "rule": RULE,
                "tie_break": TIE_BREAK,
                "mission": str(order.get("mission") or ""),
                "brief_sha": brief,
                "plan_pins": pins,
                "contestants": roster,
            },
        )

    @staticmethod
    def _text(path: Path) -> str | None:
        """Live file or the open field generation. Symlinks do not count."""
        if not field_is_file(path):
            return None
        return field_read_text(path)

    @staticmethod
    def _read_round(root: Path) -> dict[str, Any] | None:
        text = Campo._text(Campo.arena(root) / "round.json")
        if text is None:
            return None
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return None
        return raw if isinstance(raw, dict) else None

    @staticmethod
    def _roster_ids(rnd: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for row in rnd.get("contestants") or []:
            if isinstance(row, dict) and str(row.get("id") or "").strip():
                ids.append(str(row["id"]))
        return ids

    @staticmethod
    def _ballots(
        root: Path, roster: list[str]
    ) -> list[dict[str, str]] | None:
        found: list[dict[str, str]] = []
        arena = Campo.arena(root)
        allowed = set(roster)
        for cid in roster:
            proposal = arena / "proposals" / f"{cid}.md"
            ballot_path = arena / "ballots" / f"{cid}.json"
            body = Campo._text(proposal)
            if body is None or not body.strip():
                return None
            ballot = Campo._one_ballot(ballot_path, cid, allowed)
            if ballot is None:
                return None
            found.append(ballot)
        return found

    @staticmethod
    def _one_ballot(
        path: Path, contestant_id: str, allowed: set[str]
    ) -> dict[str, str] | None:
        text = Campo._text(path)
        if text is None:
            return None
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(raw, dict):
            return None
        if str(raw.get("contestant") or "") != contestant_id:
            return None
        claim = str(raw.get("claim") or "").strip()
        evidence = str(raw.get("evidence") or "").strip()
        peer = str(raw.get("peer") or "").strip()
        stance = str(raw.get("stance") or "").strip().lower()
        if not claim or not evidence:
            return None
        if stance not in STANCES:
            return None
        if peer not in allowed or peer == contestant_id:
            return None
        return {
            "contestant": contestant_id,
            "claim": claim,
            "evidence": evidence,
            "peer": peer,
            "stance": stance,
        }

    @staticmethod
    def _elect(
        roster: list[str], ballots: list[dict[str, str]]
    ) -> tuple[str, dict[str, int]] | None:
        tally = {cid: 0 for cid in roster}
        concedes = 0
        for ballot in ballots:
            if ballot["stance"] != "concede":
                continue
            peer = ballot["peer"]
            if peer not in tally:
                continue
            tally[peer] += 1
            concedes += 1
        if concedes < 1:
            return None
        best = max(tally.values())
        winners = sorted(cid for cid, score in tally.items() if score == best)
        return winners[0], tally

    @staticmethod
    def _fidelity_block(root: Path, rnd: dict[str, Any]) -> str | None:
        from of.regime import PlanIngress

        order = load_order(root)
        want_brief = str(rnd.get("brief_sha") or "")
        if want_brief:
            spec_text = Campo._text(spec_path(root))
            if spec_text is None or sha256_text(spec_text) != want_brief:
                return "campo pin refused: SPEC drifted from the verbatim brief"
        if str(order.get("mission") or "") != str(rnd.get("mission") or ""):
            return "campo pin refused: ORDER mission drifted from the pinned brief"
        got_pins = [
            {"rel": rel, "sha": digest}
            for rel, digest in PlanIngress.pinned(order)
        ]
        if list(rnd.get("plan_pins") or []) != got_pins:
            return "campo pin refused: plan_source pin drifted"
        doc = PlanIngress.document(root, order)
        if doc.get("hot"):
            note = str(doc.get("note") or doc.get("status") or "plan_fidelity")
            return f"campo pin refused: {note}"
        return None

    @staticmethod
    def _pin(
        root: Path,
        rnd: dict[str, Any],
        leader: str,
        tally: dict[str, int],
    ) -> None:
        arena = Campo.arena(root)
        raw = field_read_bytes(order_path(root))
        if raw is None:
            die("campo pin refused: ORDER missing")
        dump_bytes(arena / "ORDER.json", raw)
        roster = Campo._roster_ids(rnd)
        crew = [cid for cid in roster if cid != leader]
        dump_json(
            Campo._leader_path(root),
            {
                "v": 1,
                "leader": leader,
                "crew": crew,
                "rule": RULE,
                "tie_break": TIE_BREAK,
                "tally": tally,
                "order_sha": sha256_text(raw.decode("utf-8")),
            },
        )
        nxt = dict(rnd)
        nxt["status"] = "pinned"
        nxt["leader"] = leader
        nxt["crew"] = crew
        dump_json(arena / "round.json", nxt)

    @staticmethod
    def _leader_path(root: Path) -> Path:
        return Campo.arena(root) / "leader.json"

    @staticmethod
    def _open_doc(root: Path, reason: str) -> dict[str, Any]:
        del root
        return {
            "pinned": False,
            "status": "open",
            "leader": None,
            "crew": [],
            "reason": reason,
        }

    @staticmethod
    def _pinned_doc(root: Path, rnd: dict[str, Any]) -> dict[str, Any]:
        text = Campo._text(Campo._leader_path(root))
        try:
            leader_doc = json.loads(text) if text else {}
        except json.JSONDecodeError:
            leader_doc = {}
        if not isinstance(leader_doc, dict):
            leader_doc = {}
        leader = str(leader_doc.get("leader") or rnd.get("leader") or "")
        crew = list(leader_doc.get("crew") or rnd.get("crew") or [])
        return {
            "pinned": True,
            "status": "pinned",
            "leader": leader,
            "crew": [str(item) for item in crew],
            "reason": "",
            "rule": str(leader_doc.get("rule") or RULE),
            "tally": leader_doc.get("tally") or {},
        }
