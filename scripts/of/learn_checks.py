"""Repeated residual claims become a proposed check. Accept writes it."""
from __future__ import annotations

import hashlib
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

WANTS = frozenset({"mission", "phase", "constraints", "done_when", "workspace"})
STATUSES = frozenset({"done", "blocked", "threshold"})
KINDS = ("redesign", "check", "run", "prose")
UNRESOLVED = frozenset({"blocked", "threshold"})


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
    if status not in STATUSES:
        return None
    inner = doc.get("residual")
    if not isinstance(inner, dict):
        return None
    raw_wants = inner.get("wants_to_change") or []
    if not isinstance(raw_wants, list):
        raw_wants = []
    wants = _texts([item for item in raw_wants if item in WANTS])
    patch = inner.get("proposed_patch") or {}
    if patch is None:
        patch = {}
    if not isinstance(patch, dict):
        return None
    failed = _texts(patch.get("requirements_failed"))
    constraints = _texts(patch.get("constraints+"))
    done_when = _texts(patch.get("done_when+"))
    if status not in UNRESOLVED and not failed:
        return None
    if not (wants or failed or constraints or done_when):
        return None
    return {
        "status": status,
        "wants": list(wants),
        "failed": list(failed),
        "constraints": list(constraints),
        "done_when": list(done_when),
    }


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
    def repeated(root: Path) -> list[dict[str, Any]]:
        grouped: dict[str, set[str]] = {}
        payloads: dict[str, dict[str, Any]] = {}
        for fid, home, _order in list_field_homes(root):
            if home.is_symlink():
                continue
            waves = home / "waves"
            if not waves.is_dir() or waves.is_symlink():
                continue
            for wave in sorted(waves.iterdir()):
                residuals = wave / "residuals"
                if (
                    not wave.is_dir()
                    or wave.is_symlink()
                    or not residuals.is_dir()
                    or residuals.is_symlink()
                ):
                    continue
                for path in sorted(residuals.glob("*.json")):
                    if path.is_symlink():
                        continue
                    doc = _read_json_object(path)
                    if not isinstance(doc, dict):
                        continue
                    payload = _payload(doc)
                    if payload is None:
                        continue
                    key = _key(payload)
                    grouped.setdefault(key, set()).add(fid)
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
    def proposals(root: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for claim in LearnChecks.repeated(root):
            key = str(claim["key"])
            payload = claim["payload"]
            for kind in LearnChecks._kinds(payload):
                path = "AGENTS.md" if kind == "prose" else LearnChecks.script_rel(key)
                rows.append(
                    {
                        "id": f"chk_{key}_{kind}",
                        "key": key,
                        "kind": kind,
                        "message": claim["message"],
                        "path": path,
                        "fields": claim["fields"],
                        "command": LearnChecks.command(key) if kind == "run" else "",
                    }
                )
        return rows

    @staticmethod
    def _proposal(root: Path, proposal_id: str) -> dict[str, Any]:
        key = str(proposal_id or "").strip()
        for row in LearnChecks.proposals(root):
            if row["id"] == key:
                return row
        die(
            f"no check {key}; of learn --checks lists a proposal "
            "when the same residual is in two fields"
        )
        raise AssertionError("die")

    @staticmethod
    def _script(message: str, payload: dict[str, Any]) -> str:
        data = {
            "message": message,
            "needles": list(payload["constraints"]) + list(payload["done_when"]),
            "claim": payload,
        }
        encoded = json.dumps(json.dumps(data, ensure_ascii=False))
        return (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            f"DATA = json.loads({encoded})\n"
            "WANTS = {'mission', 'phase', 'constraints', 'done_when', 'workspace'}\n"
            "\n"
            "def texts(value):\n"
            "    if not isinstance(value, list):\n"
            "        return []\n"
            "    found = []\n"
            "    for item in value:\n"
            "        if not isinstance(item, str):\n"
            "            continue\n"
            "        text = item.strip()\n"
            "        if text and text not in found:\n"
            "            found.append(text)\n"
            "    found.sort()\n"
            "    return found\n"
            "\n"
            "def payload(doc):\n"
            "    if not isinstance(doc, dict):\n"
            "        return None\n"
            "    status = doc.get('status')\n"
            "    if status not in {'done', 'blocked', 'threshold'}:\n"
            "        return None\n"
            "    inner = doc.get('residual')\n"
            "    if not isinstance(inner, dict):\n"
            "        return None\n"
            "    raw = inner.get('wants_to_change') or []\n"
            "    if not isinstance(raw, list):\n"
            "        raw = []\n"
            "    wants = texts([item for item in raw if item in WANTS])\n"
            "    patch = inner.get('proposed_patch') or {}\n"
            "    if not isinstance(patch, dict):\n"
            "        return None\n"
            "    failed = texts(patch.get('requirements_failed'))\n"
            "    constraints = texts(patch.get('constraints+'))\n"
            "    done_when = texts(patch.get('done_when+'))\n"
            "    if status == 'done' and not failed:\n"
            "        return None\n"
            "    if not (wants or failed or constraints or done_when):\n"
            "        return None\n"
            "    return {\n"
            "        'status': status,\n"
            "        'wants': wants,\n"
            "        'failed': failed,\n"
            "        'constraints': constraints,\n"
            "        'done_when': done_when,\n"
            "    }\n"
            "\n"
            "def homes(root):\n"
            "    of = root / '.orderfield'\n"
            "    fields = of / 'fields'\n"
            "    found = []\n"
            "    if fields.is_dir() and not fields.is_symlink():\n"
            "        for home in sorted(p for p in fields.iterdir() if p.is_dir() and not p.is_symlink()):\n"
            "            order = home / 'ORDER.json'\n"
            "            if order.is_file() and not order.is_symlink():\n"
            "                found.append(home)\n"
            "    if found:\n"
            "        return found\n"
            "    if (of / 'ORDER.json').is_file() and not (of / 'ORDER.json').is_symlink():\n"
            "        return [of]\n"
            "    return []\n"
            "\n"
            "def order_text(root):\n"
            "    parts = []\n"
            "    for home in homes(root):\n"
            "        try:\n"
            "            doc = json.loads((home / 'ORDER.json').read_text(encoding='utf-8'))\n"
            "        except (OSError, json.JSONDecodeError):\n"
            "            continue\n"
            "        if not isinstance(doc, dict):\n"
            "            continue\n"
            "        for key in ('constraints', 'done_when'):\n"
            "            for item in doc.get(key) or []:\n"
            "                parts.append(str(item))\n"
            "    return '\\n'.join(parts)\n"
            "\n"
            "def matched(root):\n"
            "    for home in homes(root):\n"
            "        waves = home / 'waves'\n"
            "        if not waves.is_dir() or waves.is_symlink():\n"
            "            continue\n"
            "        for wave in waves.iterdir():\n"
            "            residuals = wave / 'residuals'\n"
            "            if not wave.is_dir() or wave.is_symlink() or not residuals.is_dir() or residuals.is_symlink():\n"
            "                continue\n"
            "            for path in residuals.glob('*.json'):\n"
            "                if path.is_symlink():\n"
            "                    continue\n"
            "                try:\n"
            "                    doc = json.loads(path.read_text(encoding='utf-8'))\n"
            "                except (OSError, json.JSONDecodeError):\n"
            "                    continue\n"
            "                if payload(doc) == DATA['claim']:\n"
            "                    return True\n"
            "    return False\n"
            "\n"
            "def main():\n"
            "    root = Path(__file__).resolve().parents[2]\n"
            "    needles = DATA['needles']\n"
            "    if needles:\n"
            "        text = order_text(root)\n"
            "        if any(needle not in text for needle in needles):\n"
            "            print(DATA['message'], file=sys.stderr)\n"
            "            return 1\n"
            "        return 0\n"
            "    if matched(root):\n"
            "        print(DATA['message'], file=sys.stderr)\n"
            "        return 1\n"
            "    return 0\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
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
    def _claim(root: Path, key: str) -> dict[str, Any]:
        for claim in LearnChecks.repeated(root):
            if claim["key"] == key:
                return claim
        die(
            f"no repeated residual {key}; of learn --checks "
            "after the same residual is in two fields"
        )
        raise AssertionError("die")

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
    def _land_prose(root: Path, message: str) -> None:
        dest = LearnChecks._dest(root, "AGENTS.md")
        line = f"- {message}"
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
        row = LearnChecks._proposal(root, proposal_id)
        claim = LearnChecks._claim(root, str(row["key"]))
        payload = claim["payload"]
        message = str(claim["message"])
        kind = str(row["kind"])
        if kind in {"redesign", "check", "run"}:
            LearnChecks._write(
                root,
                LearnChecks.script_rel(str(row["key"])),
                LearnChecks._script(message, payload),
            )
        if kind == "redesign":
            LearnChecks._land_contract(root, payload)
        elif kind == "run":
            LearnChecks._land_run(root, str(row["key"]))
        elif kind == "prose":
            LearnChecks._land_prose(root, message)
        return row
