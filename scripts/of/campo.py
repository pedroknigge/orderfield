"""Campo: written arena, peer election, pin of ORDER + leader.

Deep module. Init and pack call this interface. Ballot rules, plurality
math, tie-break, and the verbatim ORDER snapshot stay here.

Contestants and crew share the field cwd and git branch. This module does
not create a worktree and does not accept a host-appointed leader.

Re-open after verifier refuse is parent epic #333, not this slice.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from of_adapters import AdapterHints

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
    spec_path,
)

CONFIG_ENV = "OF_CONFIG"
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
STANCES = frozenset({"concede", "challenge"})
RULE = "plurality-concede"
TIE_BREAK = "contestant-id"


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
            return {"v": 1, "effort": AdapterHints.DEFAULT_EFFORT, "models": []}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            die(f"invalid campo config {path}: {exc}")
        if not isinstance(raw, dict):
            die(f"invalid campo config {path}: expected an object")
        effort = str(raw.get("effort") or AdapterHints.DEFAULT_EFFORT).strip()
        if effort not in AdapterHints.EFFORTS:
            die(
                f"campo config effort must be {'|'.join(sorted(AdapterHints.EFFORTS))}"
            )
        models = raw.get("models") or []
        if not isinstance(models, list):
            die(f"invalid campo config {path}: models must be a list")
        clean = [Campo._model(str(item)) for item in models]
        return {"v": 1, "effort": effort, "models": clean}

    @staticmethod
    def write_defaults(models: list[str], effort: str | None = None) -> dict[str, Any]:
        clean = [Campo._model(item) for item in models]
        if len(clean) < 2:
            die("of config set needs at least two --model values")
        picked = str(effort or AdapterHints.DEFAULT_EFFORT).strip()
        if picked not in AdapterHints.EFFORTS:
            die(
                f"--effort must be {'|'.join(sorted(AdapterHints.EFFORTS))} "
                f"(got {picked!r})"
            )
        doc = {"v": 1, "effort": picked, "models": clean}
        dump_json(Campo.config_path(), doc)
        return doc

    @staticmethod
    def contestants(doc: dict[str, Any] | None = None) -> list[dict[str, str]]:
        cfg = doc if doc is not None else Campo.read_config()
        effort = str(cfg.get("effort") or AdapterHints.DEFAULT_EFFORT)
        rows: list[dict[str, str]] = []
        for index, model in enumerate(cfg.get("models") or [], start=1):
            rows.append(
                {"id": f"c{index}", "model": str(model), "effort": effort}
            )
        return rows

    @staticmethod
    def require_roster() -> list[dict[str, str]]:
        rows = Campo.contestants()
        if len(rows) < 2:
            die(
                "campo needs N>=2 contestants; "
                "of config set --model A --model B --effort medium"
            )
        return rows

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
        if not MODEL_RE.match(model):
            die(f"invalid --model {raw!r}")
        return model

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
