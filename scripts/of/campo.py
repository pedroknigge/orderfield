"""Campo: written arena, peer election, pin of ORDER + leader.

Deep module. Init and pack call this interface. Ballot rules, plurality
math, tie-break, and the verbatim ORDER snapshot stay here.

Contestants and crew share the field cwd and git branch. A commit on that
branch is how the others catch up (proposals, ballots, code, residual
notes). The session that runs of is contestant #1, a peer, not a parent.
This module launches the other peers headless on this cwd and branch,
waits for ballots or a deadline, then settles. It does not create a
worktree, does not run a merge-packet, and does not accept a
host-appointed leader. Two writers do not edit one path at once.

Re-open after verifier refuse is parent epic #333, not this slice.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from of_adapters import (
    ADAPTER_BINS,
    AdapterDetect,
    AdapterHints,
    build_spawn_argv,
    detect_adapters,
    spawn_env,
    which_bin,
)

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
# Strict majority, and c1 must have voted. N=3 needs 2 ballots including c1.
DEFAULT_DEADLINE_S = 120.0
DEADLINE_ENV = "OF_CAMPO_DEADLINE"
# macOS keeps mkdir/cat/sh in /bin. A leader PATH that is only a stub dir
# plus git (/usr/bin) cannot run them. Children keep the leader entries first.
_SYSTEM_PATH = ("/bin", "/usr/bin")
_STDERR_TAIL = 400


class Campo:
    """Public surface: config, enter, settle, hold_pack. Election stays inside.

    Launch, wait, deadline, dead-child, quorum, and settle stay in this module.
    """

    # (argv, cwd, env) -> process with pid, poll, wait, kill, returncode.
    # None uses subprocess.Popen on this cwd. Tests inject a fake.
    runner: Callable[..., Any] | None = None
    _children: list[Any] = []

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

    GATE_NEXT = (
        "of config set --contestant MODEL EFFORT (xN) then of new --campo"
    )

    @staticmethod
    def roster_ready(doc: dict[str, Any] | None = None) -> bool:
        return len(Campo.contestants(doc)) >= 2

    @staticmethod
    def refuse_unset_roster() -> None:
        die(Campo.GATE_NEXT)

    @staticmethod
    def resolve_entry(args) -> bool:
        """Return True when this init/new should enter Campo.

        Refusal (roster unset, no --orden-only) happens before any field write.
        --orden-only is the explicit plain-Orden escape. With a stored roster,
        Campo is the default unless --orden-only. --campo stays the explicit
        verb and the of init alias of of new --campo.
        """
        orden_only = bool(getattr(args, "orden_only", False))
        want_flag = bool(getattr(args, "campo", False))
        if orden_only and want_flag:
            die("pass only one of --campo / --orden-only")
        if orden_only:
            return False
        if want_flag:
            Campo.require_roster()
            return True
        if Campo.roster_ready():
            return True
        Campo.refuse_unset_roster()
        return False  # unreachable

    @staticmethod
    def require_roster() -> list[dict[str, str]]:
        rows = Campo.contestants()
        if len(rows) < 2:
            die(Campo.GATE_NEXT)
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
    def invoking_harness(order: dict[str, Any] | None = None) -> str:
        """Session that is running of. Origin stamp, else OF_ORIGIN, else PATH."""
        if isinstance(order, dict):
            origin = order.get("origin")
            if isinstance(origin, dict):
                stamped = str(origin.get("harness") or "").strip().lower()
                if stamped:
                    return stamped
        env = (os.environ.get("OF_ORIGIN") or "").strip().lower()
        if env:
            return env
        from of_adapters import pick_adapter

        return pick_adapter(None)

    @staticmethod
    def deadline_s() -> float:
        """Seconds to wait for ballots. OF_CAMPO_DEADLINE overrides 120."""
        raw = (os.environ.get(DEADLINE_ENV) or "").strip()
        if not raw:
            return DEFAULT_DEADLINE_S
        try:
            value = float(raw)
        except ValueError:
            die(f"invalid {DEADLINE_ENV} {raw!r}")
        if value < 0:
            die(f"invalid {DEADLINE_ENV} {raw!r}")
        return value

    @staticmethod
    def quorum(roster: list[str], ballots: list[dict[str, str]]) -> bool:
        """Strict majority, c1 included, and at least one concede.

        N=2 needs both ballots. N=3 needs 2 including c1. N=4 needs 3
        including c1. Absent peers stay in the tally at 0 and can still
        receive concedes. c1 alone never pins.
        """
        if not roster:
            return False
        need = len(roster) // 2 + 1
        present = {str(row.get("contestant") or "") for row in ballots}
        if "c1" not in present or len(present) < need:
            return False
        return any(str(row.get("stance") or "") == "concede" for row in ballots)

    @staticmethod
    def peer_plan(
        order: dict[str, Any], roster: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        """c1 is the invoking session. c2..N are headless peers on this cwd."""
        invoker = Campo.invoking_harness(order)
        planned: list[dict[str, Any]] = []
        for index, seat in enumerate(roster, start=1):
            bound = Campo.resolve_spawn(seat)
            local = index == 1
            if local and bound["harness"] != invoker:
                die(
                    "campo: contestant #1 is the session running of "
                    f"(harness {invoker}); the first roster peer is "
                    f"{bound['harness']}/{bound['model']}. "
                    "Put that session's model first. It stays a peer"
                )
            row: dict[str, Any] = {
                "id": seat["id"],
                "model": bound["model"],
                "effort": bound["effort"],
                "harness": bound["harness"],
                "mode": "local" if local else "headless",
                "peer": True,
            }
            planned.append(row)
        return planned

    @staticmethod
    def arena(root: Path) -> Path:
        return field_home(root) / "campo"

    @staticmethod
    def enter(
        root: Path,
        order: dict[str, Any],
        source_text: str | None = None,
    ) -> dict[str, Any]:
        """Open, launch c2..N, wait for ballots or the deadline, then settle."""
        del source_text  # SPEC / PlanIngress already hold the verbatim brief
        planned = Campo._open(root, order)
        Campo._launch(root, planned)
        Campo._wait(root, planned)
        Campo._write_spawns(root, planned)
        return Campo.settle(root, live=True)

    @staticmethod
    def settle(root: Path, *, live: bool = False) -> dict[str, Any]:
        """Elect from disk ballots. No leader argument. No worktree.

        live=True is the init path: ballots children just wrote are not in
        the open field generation, and a missed deadline may pin a quorum
        or write campo/hold.json. The manual retry (of campo settle) keeps
        live=False and still requires every ballot.
        """
        rnd = Campo._read_round(root)
        if rnd is None:
            die("campo is not open; of new --campo")
        if rnd.get("status") == "pinned" and Campo._leader_path(root).is_file():
            return Campo._pinned_doc(root, rnd)
        roster = Campo._roster_ids(rnd)
        ballots = Campo._ballots(root, roster, live=live)
        if ballots is None and live:
            present = Campo._ballots(root, roster, live=True, partial=True) or []
            if Campo.quorum(roster, present):
                ballots = present
            else:
                return Campo._hold(root, roster, present)
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
        if doc.get("hitl"):
            heads = ",".join(str(item) for item in (doc.get("headless") or []))
            missing = " ".join(
                f"campo/ballots/{cid}.json" for cid in (doc.get("missing") or [])
            )
            lines = [
                (
                    f"campo        hold  invoker={doc.get('invoker')} peer  "
                    f"headless={heads or '-'}  {doc.get('reason')}"
                ),
                f"next         write {missing} then of campo settle",
            ]
            lines.extend(Campo._peer_lines(doc.get("peer_diag") or []))
            return lines
        reason = str(doc.get("reason") or "ballots incomplete")
        extra = ""
        if doc.get("invoker"):
            heads = ",".join(str(item) for item in (doc.get("headless") or []))
            extra = (
                f"  invoker={doc['invoker']} peer  headless={heads or '-'}"
            )
        return [
            f"campo        open  {reason}{extra}",
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
    def _open(root: Path, order: dict[str, Any]) -> list[dict[str, Any]]:
        roster = Campo.require_roster()
        planned = Campo.peer_plan(order, roster)
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
        seats = [
            {"id": row["id"], "model": row["model"], "effort": row["effort"]}
            for row in planned
        ]
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
                "invoker": "c1",
                "contestants": seats,
            },
        )
        return planned

    @staticmethod
    def _stamp() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def _public_peer(row: dict[str, Any]) -> dict[str, Any]:
        keep = (
            "id",
            "model",
            "effort",
            "harness",
            "mode",
            "peer",
            "argv",
            "launched",
            "pid",
            "started",
            "ended",
            "code",
            "status",
            "stderr_tail",
        )
        return {key: row[key] for key in keep if key in row}

    @staticmethod
    def _write_spawns(root: Path, planned: list[dict[str, Any]]) -> None:
        dump_json(
            Campo.arena(root) / "spawns.json",
            {
                "v": 1,
                "stub": False,
                "invoker": "c1",
                "cwd": ".",
                "deadline_s": Campo.deadline_s(),
                "note": (
                    "c1 is the session running of, a peer. "
                    "c2..N are launched headless on this cwd and branch. "
                    "No worktree."
                ),
                "peers": [Campo._public_peer(row) for row in planned],
            },
        )

    @staticmethod
    def _peer_prompt(row: dict[str, Any]) -> str:
        cid = row["id"]
        return (
            f"You are campo peer {cid} ({row['model']}), a peer on this git "
            "branch and this cwd. Write "
            f".orderfield/campo/proposals/{cid}.md and "
            f".orderfield/campo/ballots/{cid}.json with contestant, claim, "
            "evidence, peer, and stance (concede or challenge). Commit that "
            "on this branch. Do not create a worktree."
        )

    @staticmethod
    def _kill(proc: Any) -> None:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            return

    @staticmethod
    def _launch(root: Path, planned: list[dict[str, Any]]) -> None:
        """Start c2..N. A missing CLI dies before any process is created."""
        headless = [row for row in planned if row.get("mode") == "headless"]
        for row in headless:
            harness = str(row["harness"])
            names = list(ADAPTER_BINS.get(harness) or [])
            if not names or which_bin(names) is None:
                die(
                    "campo launch refused: "
                    f"{harness} CLI is not on PATH "
                    f"(peer {row['id']} model {row['model']})"
                )
        started: list[Any] = []
        try:
            for row in headless:
                packet = {
                    "child_id": row["id"],
                    "adapter_hints": {
                        "model": row["model"],
                        "effort": row["effort"],
                    },
                }
                residual = Campo.arena(root) / "peers" / f"{row['id']}.out"
                residual.parent.mkdir(parents=True, exist_ok=True)
                argv = build_spawn_argv(
                    str(row["harness"]),
                    Campo._peer_prompt(row),
                    packet,
                    residual,
                )
                env = spawn_env(str(row["harness"]))
                env["OF_CAMPO_ID"] = str(row["id"])
                env["OF_CAMPO_ROOT"] = str(root)
                Campo._ensure_system_path(env)
                runner = Campo.runner
                err_fh = None
                if runner is None:
                    err_path = Campo.arena(root) / "peers" / f"{row['id']}.err"
                    err_fh = err_path.open("wb", buffering=0)
                    row["_err_fh"] = err_fh
                    row["_err_path"] = err_path
                if runner is not None:
                    proc = runner(argv, root, env)
                else:
                    proc = subprocess.Popen(
                        argv,
                        cwd=str(root),
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=err_fh,
                    )
                row["argv"] = list(argv)
                row["launched"] = True
                row["pid"] = int(getattr(proc, "pid", 0) or 0)
                row["started"] = Campo._stamp()
                row["status"] = "running"
                row["_proc"] = proc
                started.append(proc)
        except BaseException:
            for proc in started:
                Campo._kill(proc)
            for row in headless:
                Campo._capture_stderr(row)
            raise
        Campo._children = started
        Campo._write_spawns(root, planned)

    @staticmethod
    def _wait(root: Path, planned: list[dict[str, Any]]) -> None:
        roster = [str(row["id"]) for row in planned]
        deadline = time.monotonic() + Campo.deadline_s()
        while True:
            if Campo._ballots(root, roster, live=True) is not None:
                Campo._reap(root, planned, force=False)
                Campo._write_spawns(root, planned)
                return
            if time.monotonic() >= deadline:
                Campo._reap(root, planned, force=True)
                Campo._write_spawns(root, planned)
                return
            time.sleep(0.05)

    @staticmethod
    def _reap(root: Path, planned: list[dict[str, Any]], *, force: bool) -> None:
        roster = [str(row["id"]) for row in planned]
        allowed = set(roster)
        arena = Campo.arena(root)
        for row in planned:
            proc = row.get("_proc")
            if proc is None:
                continue
            code = proc.poll()
            if code is None and force:
                Campo._kill(proc)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                row["status"] = "timeout"
                row["code"] = proc.poll()
                row["ended"] = Campo._stamp()
                Campo._capture_stderr(row)
                continue
            if code is None:
                row["status"] = "running"
                continue
            row["code"] = int(code)
            row["ended"] = Campo._stamp()
            Campo._capture_stderr(row)
            ballot = Campo._one_ballot(
                arena / "ballots" / f"{row['id']}.json",
                str(row["id"]),
                allowed,
                Campo._disk_text,
            )
            proposal = Campo._disk_text(arena / "proposals" / f"{row['id']}.md")
            ready = (
                ballot is not None
                and proposal is not None
                and bool(proposal.strip())
            )
            row["status"] = "exited" if code == 0 and ready else "dead"

    @staticmethod
    def _hold(
        root: Path, roster: list[str], present: list[dict[str, str]]
    ) -> dict[str, Any]:
        have = [row["contestant"] for row in present]
        have_set = set(have)
        missing = [cid for cid in roster if cid not in have_set]
        reason = (
            "quorum missed at deadline"
            f"; have {','.join(have) or '-'}"
            f"; missing {','.join(missing) or '-'}"
        )
        diag = Campo._peer_diag(root)
        dump_json(
            Campo.arena(root) / "hold.json",
            {
                "v": 1,
                "reason": reason,
                "deadline": Campo.deadline_s(),
                "have": have,
                "missing": missing,
                "hitl": True,
                "peers": diag,
            },
        )
        doc = Campo._open_doc(root, reason)
        doc["hitl"] = True
        doc["have"] = have
        doc["missing"] = missing
        doc["peer_diag"] = diag
        return doc

    @staticmethod
    def _ensure_system_path(env: dict[str, str]) -> None:
        """Append /bin and /usr/bin when the leader PATH does not have them.

        Leader entries stay first, so a stub dir still wins. macOS git lives
        in /usr/bin while mkdir and cat live in /bin; without /bin a headless
        peer exits 0 and writes no ballot.
        """
        parts = [part for part in (env.get("PATH") or "").split(os.pathsep) if part]
        have = set(parts)
        for entry in _SYSTEM_PATH:
            if entry in have:
                continue
            if Path(entry).is_dir():
                parts.append(entry)
                have.add(entry)
        if parts:
            env["PATH"] = os.pathsep.join(parts)

    @staticmethod
    def _capture_stderr(row: dict[str, Any]) -> None:
        handle = row.pop("_err_fh", None)
        if handle is not None:
            try:
                handle.flush()
                handle.close()
            except OSError:
                pass
        path = row.pop("_err_path", None)
        if path is None:
            return
        tail = Campo._stderr_tail(Path(path))
        if tail:
            row["stderr_tail"] = tail

    @staticmethod
    def _stderr_tail(path: Path) -> str:
        text = Campo._disk_text(path)
        if not text:
            return ""
        text = text.replace("\x00", "").strip()
        if len(text) <= _STDERR_TAIL:
            return text
        return text[-_STDERR_TAIL:]

    @staticmethod
    def _peer_diag(root: Path) -> list[dict[str, Any]]:
        text = Campo._text(Campo.arena(root) / "spawns.json")
        try:
            raw = json.loads(text) if text else {}
        except json.JSONDecodeError:
            raw = {}
        peers = raw.get("peers") if isinstance(raw, dict) else None
        if not isinstance(peers, list):
            return []
        diag: list[dict[str, Any]] = []
        for row in peers:
            if not isinstance(row, dict) or row.get("mode") != "headless":
                continue
            item: dict[str, Any] = {
                "id": str(row.get("id") or ""),
                "status": row.get("status"),
                "code": row.get("code"),
            }
            tail = str(row.get("stderr_tail") or "").strip()
            if tail:
                item["stderr_tail"] = tail
            diag.append(item)
        return diag

    @staticmethod
    def _peer_lines(diag: list[Any]) -> list[str]:
        lines: list[str] = []
        for row in diag:
            if not isinstance(row, dict):
                continue
            err = " ".join(str(row.get("stderr_tail") or "").split())
            if len(err) > 180:
                err = err[-180:]
            line = (
                f"peer         {row.get('id')} {row.get('status')} "
                f"code={row.get('code')}"
            )
            if err:
                line += f" stderr={err}"
            lines.append(line)
        return lines

    @staticmethod
    def _text(path: Path) -> str | None:
        """Live file or the open field generation. Symlinks do not count."""
        if not field_is_file(path):
            return None
        return field_read_text(path)

    @staticmethod
    def _disk_text(path: Path) -> str | None:
        """Bytes on disk, ignoring the open field generation.

        Children write ballots with normal IO while init still holds the
        generation. The generation snapshot does not contain those files.
        """
        try:
            if not path.is_file() or path.is_symlink():
                return None
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

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
        root: Path,
        roster: list[str],
        *,
        live: bool = False,
        partial: bool = False,
    ) -> list[dict[str, str]] | None:
        read = Campo._disk_text if live else Campo._text
        found: list[dict[str, str]] = []
        arena = Campo.arena(root)
        allowed = set(roster)
        for cid in roster:
            proposal = arena / "proposals" / f"{cid}.md"
            ballot_path = arena / "ballots" / f"{cid}.json"
            body = read(proposal)
            ballot = Campo._one_ballot(ballot_path, cid, allowed, read)
            if body is None or not body.strip() or ballot is None:
                if partial:
                    continue
                return None
            found.append(ballot)
        return found

    @staticmethod
    def _one_ballot(
        path: Path,
        contestant_id: str,
        allowed: set[str],
        read: Callable[[Path], str | None] | None = None,
    ) -> dict[str, str] | None:
        text = (read or Campo._text)(path)
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
        hold = arena / "hold.json"
        try:
            if hold.is_file() and not hold.is_symlink():
                hold.unlink()
        except OSError:
            pass
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
        text = Campo._text(Campo.arena(root) / "spawns.json")
        peers: list[Any] = []
        try:
            raw = json.loads(text) if text else {}
        except json.JSONDecodeError:
            raw = {}
        if isinstance(raw, dict) and isinstance(raw.get("peers"), list):
            peers = raw["peers"]
        headless = [
            str(row.get("id"))
            for row in peers
            if isinstance(row, dict) and row.get("mode") == "headless"
        ]
        invoker = None
        if isinstance(raw, dict) and raw.get("invoker"):
            invoker = str(raw["invoker"])
        return {
            "pinned": False,
            "status": "open",
            "leader": None,
            "crew": [],
            "reason": reason,
            "invoker": invoker,
            "headless": headless,
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
