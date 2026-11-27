"""Repeated residual claims become a proposed check. Accept writes it."""
from __future__ import annotations

import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any

from of.field import (
    PHASES,
    _read_json_object,
    _symlink_component,
    die,
    dump_json,
    list_field_homes,
    load_order,
    load_state,
    save_order,
    write_phase_md,
)


def _occurrence_identity(doc: dict) -> str:
    return str(doc.get("packet_id") or "") or hashlib.sha256(
        json.dumps(doc, sort_keys=True).encode()
    ).hexdigest()


def _residual_claims(home: Path):
    waves = home / "waves"
    if home.is_symlink() or waves.is_symlink():
        return
    for path in sorted(waves.glob("*/residuals/*.json")):
        if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
            continue
        doc = _read_json_object(path)
        if doc is None:
            continue
        claim = _payload(doc)
        if claim:
            # New packets can reuse a child path. Old residuals may lack a packet ID.
            occurrence = [path.relative_to(home).as_posix(), _occurrence_identity(doc)]
            yield occurrence, claim, _phase_target(doc) if claim["wants"] == ["phase"] else None


def _phase_target(doc: dict) -> str | None:
    evidence = str(doc["residual"].get("evidence") or "")
    targets = set()
    for line in evidence.lower().splitlines():
        match = re.fullmatch(
            r"(?:\w+ is complete,\s*)?(?:advance to|of phase) (\w+)\.?", line.strip()
        )
        if match and match[1] in PHASES:
            targets.add(match[1])
    return targets.pop() if len(targets) == 1 else None


def _texts(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    found: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in found:
            found.append(text)
    return tuple(sorted(found))


def _payload(doc: dict[str, Any]) -> dict[str, Any] | None:
    status = doc.get("status")
    if status not in ("done", "blocked", "threshold"):
        return None
    inner = doc.get("residual")
    if not isinstance(inner, dict):
        return None
    wants = [item for item in _texts(inner.get("wants_to_change"))
             if item in ("mission", "phase", "constraints", "done_when", "workspace")]
    patch = inner.get("proposed_patch") or {}
    if not isinstance(patch, dict):
        return None
    failed = _texts(patch.get("requirements_failed"))
    constraints = _texts(patch.get("constraints+"))
    done_when = _texts(patch.get("done_when+"))
    if status == "done" and not failed:
        return None
    if not (wants or failed or constraints or done_when):
        return None
    return {
        "status": status,
        "wants": wants,
        "failed": list(failed),
        "constraints": list(constraints),
        "done_when": list(done_when),
    }


def _check_homes(root: Path):
    field_root = root / ".orderfield"
    fields = field_root / "fields"
    if fields.is_dir() and not fields.is_symlink():
        homes = [path.parent for path in sorted(fields.glob("*/ORDER.json"))
                 if path.is_file() and not path.is_symlink() and not path.parent.is_symlink()]
        if homes:
            return homes
    order = field_root / "ORDER.json"
    return [field_root] if order.is_file() and not order.is_symlink() else []


def matching_observations(observations: Any, wave: int, input_hash: str | None) -> dict:
    if (isinstance(observations, dict) and input_hash
            and observations.get("input_hash") == input_hash and observations.get("wave") == wave):
        return observations
    return {}


def _landed_failure(home: Path, occurrence: list[str], claim: dict) -> dict:
    path = home / occurrence[0]
    wave = path.parent.parent
    report = _read_json_object(wave / "report.json") or {}
    if str(report.get("wave")).zfill(3) != wave.name or path.stem in _texts(report.get("skipped_in_flight")):
        return {}
    integration = report.get("integration")
    if not isinstance(integration, dict):
        return {}
    observations = _read_json_object(wave / "integrations/observations.json")
    matched = matching_observations(observations, report["wave"], integration.get("input_hash"))
    return _previous_failure(matched, path.stem, occurrence[1], _key(claim))


def _previous_failure(observations: dict, child: str, identity: str, claim_key: str) -> dict:
    failures = observations.get("learning_failures")
    record = failures.get(child) if isinstance(failures, dict) else None
    if isinstance(record, dict) and record.get("identity") == identity:
        if record.get("claim", claim_key) == claim_key:
            return record
    return {}


def _phase_completions_path(home: Path) -> Path:
    return home / "checks" / "learning" / "phase-completions.json"


def _check_failed(root: Path, claim: dict, history: dict) -> bool:
    terms = set()
    failed_ids = claim["failed"]
    required_terms = set(claim["constraints"] + claim["done_when"])
    for home in _check_homes(root):
        order = _read_json_object(home / "ORDER.json") or {}
        fid = str(order.get("id") or home.name)
        local_terms = set(_texts(order.get("constraints"))) | set(_texts(order.get("done_when")))
        terms.update(local_terms)
        known = {tuple(row) for row in history.get(fid, [])}
        ledger = _read_json_object(home / "REQUIREMENTS.json") or {}
        rows = {row["id"]: row for row in ledger.get("requirements") or []
                if isinstance(row, dict) and isinstance(row.get("id"), str)}
        if known and any(rows.get(rid, {}).get("status") == "failed" for rid in failed_ids):
            return True
        completed = (_read_json_object(_phase_completions_path(home)) or {}
                     if claim["wants"] == ["phase"] else {})
        for occurrence, payload, target in _residual_claims(home):
            if payload != claim or tuple(occurrence) in known:
                continue
            if not (required_terms or failed_ids):
                phase = order.get("phase")
                if target and (phase not in PHASES or PHASES.index(phase) < PHASES.index(target)):
                    if completed.get(occurrence[0], {}).get(occurrence[1]) != target:
                        return True
                continue
            landed = _landed_failure(home, occurrence, claim)
            if required_terms:
                redesigned = (*occurrence, "redesign") in known
                repaired = required_terms.intersection(_texts(landed.get("missing_terms")))
                if not local_terms.issuperset(required_terms) or not (redesigned or repaired):
                    return True
            if failed_ids and not all(
                rid in _texts(landed.get("failed")) and rows.get(rid, {}).get("status")
                in ("verified", "verified_internal", "verified_contract") for rid in failed_ids
            ):
                return True
    return not terms.issuperset(required_terms)


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _key(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:16]


class LearnChecks:
    """One residual claim, counted by field, proposed until accept."""

    @staticmethod
    def preserve_phase_completions(home: Path, from_phase: str, to_phase: str) -> None:
        # Before a backward transition, bind targets already reached to the
        # residuals present now. A packet that reports later gets no credit.
        passed = PHASES[PHASES.index(to_phase) + 1:PHASES.index(from_phase) + 1]
        if not passed:
            return
        path = _phase_completions_path(home)
        if _symlink_component(home, path):
            die(f"unsafe phase completion path: {path}")
        completed = _read_json_object(path) if path.exists() else {}
        if completed is None:
            die(f"invalid phase completion record: {path}")
        changed = False
        for (source, identity), _, target in _residual_claims(home):
            if target in passed and completed.get(source, {}).get(identity) != target:
                completed.setdefault(source, {})[identity] = target
                changed = True
        if changed:
            dump_json(path, completed)

    @staticmethod
    def landed_failures(order: dict, residuals: list[dict], packets: list[dict]) -> dict:
        """Bind the condition observed at integration to the exact packet."""
        from of.spec import residual_failed_stamps

        terms = set(order["constraints"]) | set(order["done_when"])
        records = {}
        for res, packet in zip(residuals, packets):
            claim = _payload(res)
            if not claim:
                continue
            failed, _ = residual_failed_stamps(res, packet)
            child = packet["child_id"]
            identity = _occurrence_identity(res)
            missing = sorted(set(claim["constraints"] + claim["done_when"]) - terms)
            if failed or claim["constraints"] or claim["done_when"]:
                records[child] = {
                    "identity": identity, "claim": _key(claim), "failed": failed,
                    "missing_terms": missing,
                }
        return records

    @staticmethod
    def carry_failures(records: dict, observations: dict) -> dict[str, tuple[str, ...]]:
        """Keep the first observation and identify failure stamps already applied."""
        previously_failed = {}
        for child, record in records.items():
            prior = _previous_failure(observations, child, record["identity"], record["claim"])
            if prior:
                record["missing_terms"] = list(_texts(prior.get("missing_terms")))
                previously_failed[child] = _texts(prior.get("failed"))
        return previously_failed

    @staticmethod
    def fix(payload: dict[str, Any]) -> str:
        parts = [f"add constraint {text!r}" for text in payload["constraints"]]
        parts += [f"add done_when {text!r}" for text in payload["done_when"]]
        parts += [f"requirement {req!r} is still failed" for req in payload["failed"]]
        if not parts:
            parts.append("resolve wants_to_change " + ",".join(payload["wants"]))
        return "; ".join(parts)

    @staticmethod
    def message(key: str, payload: dict[str, Any]) -> str:
        return f"FAIL {key}: {LearnChecks.fix(payload)}"

    @staticmethod
    def script_rel(key: str) -> str:
        return f"scripts/checks/{key}.py"

    @staticmethod
    def command(key: str) -> str:
        return f"python3 {LearnChecks.script_rel(key)}"

    @staticmethod
    def prose_line(payload: dict[str, Any]) -> str:
        return f"- {LearnChecks.fix(payload)}"

    @staticmethod
    def action(kind: str, key: str, payload: dict[str, Any]) -> str:
        if kind == "redesign":
            parts = [f"constraint {text!r}" for text in payload["constraints"]]
            parts += [f"done_when {text!r}" for text in payload["done_when"]]
            return "fold into the plan: " + "; ".join(parts)
        if kind == "check":
            return f"{LearnChecks.script_rel(key)} asserts {LearnChecks.message(key, payload)}"
        if kind == "run":
            command = f"`{LearnChecks.command(key)}`"
            return f"feature-map row {key} reach {command}; done_when {command}"
        if kind == "prose":
            return f"AGENTS.md: {LearnChecks.prose_line(payload)}"
        die(f"unknown check kind {kind}")
        raise AssertionError("die")

    @staticmethod
    def repeated(root: Path) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, list]] = {}
        payloads: dict[str, dict[str, Any]] = {}
        measurable_phases: dict[str, set[str]] = {}
        for fid, home, _order in list_field_homes(root):
            for occurrence, payload, target in _residual_claims(home):
                key = _key(payload)
                if target:
                    measurable_phases.setdefault(key, set()).add(fid)
                grouped.setdefault(key, {}).setdefault(fid, []).append(occurrence)
                payloads[key] = payload
        claims: list[dict[str, Any]] = []
        for key in sorted(grouped):
            fields = tuple(sorted(grouped[key]))
            if len(fields) < 2:
                continue
            payload = payloads[key]
            claims.append(
                {
                    "key": key,
                    "payload": payload,
                    "fields": fields,
                    "history": grouped[key],
                    "phase_check": len(measurable_phases.get(key, ())) >= 2,
                    "message": LearnChecks.message(key, payload),
                }
            )
        return claims

    @staticmethod
    def _kinds(payload: dict[str, Any], phase_check: bool) -> tuple[str, ...]:
        kinds: list[str] = []
        if payload["constraints"] or payload["done_when"]:
            kinds.append("redesign")
        if kinds or payload["failed"] or phase_check:
            kinds.extend(["check", "run"])
        kinds.append("prose")
        return tuple(kinds)

    @staticmethod
    def _proposals(root: Path):
        for claim in LearnChecks.repeated(root):
            key = str(claim["key"])
            payload = claim["payload"]
            for kind in LearnChecks._kinds(payload, claim["phase_check"]):
                path = "AGENTS.md" if kind == "prose" else LearnChecks.script_rel(key)
                yield claim, {
                    "id": f"chk_{key}_{kind}",
                    "key": key,
                    "kind": kind,
                    "message": LearnChecks.action(kind, key, payload),
                    "path": path,
                    "fields": claim["fields"],
                    "command": LearnChecks.command(key) if kind == "run" else "",
                }

    @staticmethod
    def proposals(root: Path) -> list[dict[str, Any]]:
        return [row for _claim, row in LearnChecks._proposals(root)]

    @staticmethod
    def _proposal(root: Path, proposal_id: str) -> tuple[dict, dict]:
        key = str(proposal_id or "").strip()
        for claim, row in LearnChecks._proposals(root):
            if row["id"] == key:
                return claim, row
        die(
            f"no check {key}; of learn --checks lists a proposal "
            "when the same residual is in two fields"
        )
        raise AssertionError("die")

    @staticmethod
    def _script(message: str, payload: dict[str, Any], history: dict) -> str:
        # These functions also run in a consumer repo without Orderfield installed.
        readers = "\n".join(inspect.getsource(fn) for fn in (
            _read_json_object, _texts, _payload, _phase_target, _occurrence_identity, _residual_claims,
            _check_homes, _canonical, _key, matching_observations, _previous_failure, _landed_failure,
            _phase_completions_path, _check_failed,
        ))
        return (
            "#!/usr/bin/env python3\n"
            f"HISTORY = {json.dumps(history, sort_keys=True)}\n"
            f"PHASES = {PHASES!r}\n"
            "import hashlib\nimport json\nimport re\nimport sys\nfrom pathlib import Path\n"
            "from typing import Any\n\n"
            f"CLAIM = {payload!r}\nMESSAGE = {message!r}\n\n"
            f"{readers}\n"
            "if __name__ == '__main__':\n"
            "    if _check_failed(Path(__file__).resolve().parents[2], CLAIM, HISTORY):\n"
            "        print(MESSAGE, file=sys.stderr)\n"
            "        raise SystemExit(1)\n"
        )

    @staticmethod
    def _dest(root: Path, rel: str) -> Path:
        if rel.startswith("/") or ".." in Path(rel).parts:
            die(f"check path escapes the repo: {rel}")
        dest = (Path(root) / rel).resolve()
        base = Path(root).resolve()
        if dest != base and base not in dest.parents:
            die(f"check path escapes the repo: {rel}")
        if dest.is_symlink():
            die(f"check path is a symlink: {rel}")
        return dest

    @staticmethod
    def _write(root: Path, rel: str, body: str) -> None:
        dest = LearnChecks._dest(root, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file():
            try:
                current = dest.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                current = None
            if current == body:
                return
        dest.write_text(body, encoding="utf-8")

    @staticmethod
    def _land_contract(root: Path, payload: dict[str, Any]) -> str | None:
        from of.pack import PacketRevStale
        from of.regime import DoneWhenEvidence, DoneWhenLint, reopen_done_when

        order = load_order(root)
        state = load_state(root)
        PacketRevStale.refuse_patch(root, int(state.get("wave") or 1), order)
        constraints = [str(item) for item in (order.get("constraints") or [])]
        done = [str(item) for item in (order.get("done_when") or [])]
        changed = False
        for text in payload["constraints"]:
            if text not in constraints:
                constraints.append(text)
                changed = True
        for text in payload["done_when"]:
            _command, problem = DoneWhenEvidence.classify(text)
            if problem:
                if text not in constraints:
                    constraints.append(text)
                    changed = True
                continue
            if text not in done:
                done.append(text)
                changed = True
        if not changed:
            return None
        order["constraints"] = constraints
        order["done_when"] = done
        DoneWhenLint.refuse(done)
        reopen_done_when(order, all_phases=True)
        order["rev"] = int(order["rev"]) + 1
        save_order(order, root)
        write_phase_md(root, order)
        return order["id"]

    @staticmethod
    def _land_run(root: Path, key: str) -> None:
        from of.pack import PacketRevStale
        from of.regime import DoneWhenLint, PlanFeatureMap, reopen_done_when

        order = load_order(root)
        state = load_state(root)
        PacketRevStale.refuse_patch(root, int(state.get("wave") or 1), order)
        command = LearnChecks.command(key)
        criterion = f"`{command}`"
        done = [str(item) for item in (order.get("done_when") or [])]
        if criterion not in done:
            done.append(criterion)
            DoneWhenLint.refuse(done)
            order["done_when"] = done
            reopen_done_when(order, all_phases=True)
            order["rev"] = int(order["rev"]) + 1
            save_order(order, root)
            write_phase_md(root, order)
        rows = PlanFeatureMap.load(root)
        reach = f"`{command}`"
        if not any(row["reach"] == reach for row in rows):
            rows.append({"feature": key, "reach": reach, "proof": reach})
            PlanFeatureMap.save(root, rows)

    @staticmethod
    def _land_prose(root: Path, line: str) -> None:
        dest = LearnChecks._dest(root, "AGENTS.md")
        if not line.startswith("- "):
            line = f"- {line}"
        try:
            current = dest.read_text(encoding="utf-8") if dest.is_file() else ""
        except (OSError, UnicodeDecodeError):
            current = ""
        if line in current.splitlines():
            return
        if current and not current.endswith("\n"):
            current += "\n"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(current + line + "\n", encoding="utf-8")

    @staticmethod
    def accept(root: Path, proposal_id: str) -> dict[str, Any]:
        claim, row = LearnChecks._proposal(root, proposal_id)
        payload = claim["payload"]
        kind = str(row["kind"])
        if kind in {"redesign", "check", "run"}:
            rel = LearnChecks.script_rel(str(row["key"]))
            history = claim["history"]
            path = LearnChecks._dest(root, rel)
            if path.is_file():
                # Accepting another proposal for the same claim keeps its first baseline.
                with path.open(encoding="utf-8") as existing:
                    existing.readline()
                    line = existing.readline()
                if line.startswith("HISTORY = "):
                    history = json.loads(line.removeprefix("HISTORY = "))
            repaired_field = LearnChecks._land_contract(root, payload) if kind == "redesign" else None
            if repaired_field:
                # Only a change to the field's requested terms acknowledges
                # a recurrence. Repeating an acceptance cannot clear it.
                known = history.setdefault(repaired_field, [])
                for occurrence in claim["history"].get(repaired_field, []):
                    acknowledged = [*occurrence, "redesign"]
                    if occurrence not in known and acknowledged not in known:
                        known.append(acknowledged)
            LearnChecks._write(root, rel, LearnChecks._script(
                LearnChecks.message(str(row["key"]), payload), payload, history,
            ))
        if kind == "run":
            LearnChecks._land_run(root, str(row["key"]))
        elif kind == "prose":
            LearnChecks._land_prose(root, LearnChecks.prose_line(payload))
        return row
