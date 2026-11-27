"""Repeated residual claims become a proposed check. Accept writes it."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

from of.field import (
    _read_json_object,
    die,
    list_field_homes,
    load_order,
    load_state,
    save_order,
    write_phase_md,
)


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
            identity = str(doc.get("packet_id") or "") or hashlib.sha256(
                json.dumps(doc, sort_keys=True).encode()
            ).hexdigest()
            yield [path.relative_to(home).as_posix(), identity], claim


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


def _check_failed(root: Path, claim: dict, history: dict) -> bool:
    terms = set()
    for home in _check_homes(root):
        order = _read_json_object(home / "ORDER.json") or {}
        fid = str(order.get("id") or home.name)
        for key in ("constraints", "done_when"):
            terms.update(_texts(order.get(key)))
        known = {tuple(row) for row in history.get(fid, [])}
        for occurrence, payload in _residual_claims(home):
            if payload == claim and tuple(occurrence) not in known:
                return True
        if known and claim["failed"]:
            ledger = _read_json_object(home / "REQUIREMENTS.json") or {}
            if any(isinstance(row, dict) and row.get("id") in claim["failed"]
                   and row.get("status") == "failed" for row in ledger.get("requirements") or []):
                return True
    return not terms.issuperset(claim["constraints"] + claim["done_when"])


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _key(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:16]


class LearnChecks:
    """One residual claim, counted by field, proposed until accept."""

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
        for fid, home, _order in list_field_homes(root):
            for occurrence, payload in _residual_claims(home):
                key = _key(payload)
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
                    "message": LearnChecks.message(key, payload),
                }
            )
        return claims

    @staticmethod
    def _kinds(payload: dict[str, Any]) -> tuple[str, ...]:
        kinds: list[str] = []
        if payload["constraints"] or payload["done_when"]:
            kinds.append("redesign")
        kinds.extend(["check", "run", "prose"])
        return tuple(kinds)

    @staticmethod
    def _proposals(root: Path):
        for claim in LearnChecks.repeated(root):
            key = str(claim["key"])
            payload = claim["payload"]
            for kind in LearnChecks._kinds(payload):
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
            _read_json_object, _texts, _payload, _residual_claims, _check_homes, _check_failed,
        ))
        data = json.dumps({"message": message, "claim": payload}, ensure_ascii=True)
        return (
            "#!/usr/bin/env python3\n"
            f"HISTORY = {json.dumps(history, sort_keys=True)}\n"
            "import hashlib\nimport json\nimport sys\nfrom pathlib import Path\n"
            "from typing import Any\n\n"
            f"DATA = json.loads({data!r})\n\n"
            f"{readers}\n"
            "if __name__ == '__main__':\n"
            "    if _check_failed(Path(__file__).resolve().parents[2], DATA['claim'], HISTORY):\n"
            "        print(DATA['message'], file=sys.stderr)\n"
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
    def _land_contract(root: Path, payload: dict[str, Any]) -> None:
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
            return
        order["constraints"] = constraints
        order["done_when"] = done
        DoneWhenLint.refuse(done)
        reopen_done_when(order, all_phases=True)
        order["rev"] = int(order["rev"]) + 1
        save_order(order, root)
        write_phase_md(root, order)

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
            LearnChecks._write(root, rel, LearnChecks._script(
                LearnChecks.message(str(row["key"]), payload), payload, history,
            ))
        if kind == "redesign":
            LearnChecks._land_contract(root, payload)
        elif kind == "run":
            LearnChecks._land_run(root, str(row["key"]))
        elif kind == "prose":
            LearnChecks._land_prose(root, LearnChecks.prose_line(payload))
        return row
