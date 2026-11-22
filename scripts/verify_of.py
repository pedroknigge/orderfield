#!/usr/bin/env python3
"""Install `of` from this checkout and drive one real feature.

Stdlib only. No network: `install.sh` is the checkout copy (no
`--from-release`), and `OF_NO_UPDATE_CHECK=1` keeps doctor offline.

    python3 scripts/verify_of.py --feature close-field

Evidence lands in `.cursor/skills/verify-of/runs/<run-id>/` and is not
removed when the scratch HOME and the throwaway repo are deleted.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
VERSION_FILE = ROOT / "VERSION"
DEFAULT_EVIDENCE_ROOT = ROOT / ".cursor" / "skills" / "verify-of" / "runs"
PIPE = ("doctor", "init-plan", "pack-wave", "collect-wave", "close-field")
FEATURES = PIPE + (
    "wal-resume",
    "evidence-close",
    "plan-feature-map",
    "learn-checks",
    "local-metrics",
)

CHILD = r"""
import hashlib, json, os
from pathlib import Path
root = Path.cwd()
kid = os.environ["OF_CHILD"]
pkt = json.loads((root / ".orderfield/waves/001/packets" / (kid + ".json")).read_text())
ref = ".orderfield/work/scratch/" + kid + "/notes.md"
notes = root / ref
notes.parent.mkdir(parents=True, exist_ok=True)
notes.write_text("CLI-001 pricing models mapped\n")
digest = hashlib.sha256(notes.read_bytes()).hexdigest()
res = {k: pkt[k] for k in (
    "packet_id", "packet_hash", "order_id", "order_rev", "wave", "child_id", "role")}
res.update(
    status="done",
    result_ref=ref,
    residual={
        "wants_to_change": [],
        "evidence": (
            "CLI-001: pricing models mapped\nartifact_sha: " + digest
            + "\nrollback: git checkout -- " + ref
        ),
        "proposed_patch": None,
    },
    metrics={"uncertainty": 0.1, "divergence": 0.0, "tool_failures": 0, "novelty": False},
)
out = root / pkt["residual_path"]
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(res, indent=2) + "\n")
"""


class VerifyFailed(Exception):
    """The run did not produce surviving evidence."""


def _quote(argv: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in argv)


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    log: list[str],
) -> subprocess.CompletedProcess[str]:
    log.append("$ " + _quote(argv))
    log.append(f"# cwd {cwd}")
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    log.append(f"# exit {proc.returncode}")
    if proc.stdout:
        log.append(proc.stdout.rstrip("\n"))
    if proc.stderr:
        log.append("# stderr")
        log.append(proc.stderr.rstrip("\n"))
    log.append("")
    return proc


def _require(proc: subprocess.CompletedProcess[str], argv: list[str]) -> None:
    if proc.returncode != 0:
        raise VerifyFailed(
            f"verify-of: command failed ({proc.returncode}): {_quote(argv)}"
        )


def _base_env(scratch: Path) -> dict[str, str]:
    path = os.environ.get("PATH") or "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    bindir = scratch / ".local" / "bin"
    env = {
        "PATH": str(bindir) + os.pathsep + path,
        "HOME": str(scratch),
        "TMPDIR": str(scratch / "tmp"),
        "LANG": os.environ.get("LANG") or "C.UTF-8",
        "OF_NO_UPDATE_CHECK": "1",
        "OF_NO_GC_AUTO": "1",
        "OF_LEARNINGS": str(scratch / "learnings.json"),
        "OF_SPAWN_REGISTRY": str(scratch / "spawn-registry.json"),
        "OF_UPDATE_CACHE": str(scratch / "update-check.json"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return env


def _kernel_version(doctor_text: str) -> str:
    for line in doctor_text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "kernel" and parts[2] == "ok":
            return parts[1]
    raise VerifyFailed("verify-of: doctor output has no 'kernel <version> ok' line")


def _doctor_ok(doctor_text: str) -> None:
    lines = [line.strip() for line in doctor_text.splitlines()]
    if "doctor        ok" not in lines and "doctor        ok" not in doctor_text.splitlines():
        # doctor prints two spaces groups; match the exact status line.
        if not any(line == "doctor        ok" for line in doctor_text.splitlines()):
            raise VerifyFailed("verify-of: doctor did not print 'doctor        ok'")


def _through(feature: str) -> set[str]:
    if feature not in PIPE:
        raise VerifyFailed(f"verify-of: unknown feature {feature}")
    index = PIPE.index(feature)
    return set(PIPE[: index + 1])


def _prepare_repo(work: Path, env: dict[str, str], log: list[str]) -> None:
    work.mkdir(parents=True, exist_ok=True)
    _require(
        _run(["git", "init", "-q"], cwd=work, env=env, timeout=30, log=log),
        ["git", "init", "-q"],
    )
    for argv in (
        ["git", "config", "user.email", "verify-of@example.invalid"],
        ["git", "config", "user.name", "verify-of"],
    ):
        _require(_run(argv, cwd=work, env=env, timeout=30, log=log), argv)
    _require(
        _run(
            ["git", "commit", "--allow-empty", "-q", "-m", "init"],
            cwd=work,
            env=env,
            timeout=30,
            log=log,
        ),
        ["git", "commit", "--allow-empty", "-q", "-m", "init"],
    )


def _of(
    args: list[str],
    *,
    work: Path,
    env: dict[str, str],
    log: list[str],
) -> None:
    argv = ["of", *args]
    _require(_run(argv, cwd=work, env=env, timeout=90, log=log), argv)


def _json_object(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise VerifyFailed(f"verify-of: {path.name} is not a JSON object")
    return data


def _mission(path: Path) -> str:
    mission = _json_object(path).get("mission")
    if not isinstance(mission, str):
        raise VerifyFailed(f"verify-of: {path} has no mission string")
    return mission


def _drive_wal_resume(work: Path, env: dict[str, str], log: list[str]) -> dict[str, str]:
    """Crash after the CURRENT flip, then resume until live matches CURRENT."""
    _prepare_repo(work, env, log)
    _of(
        ["init", "--mission", "committed mission", "--phase", "explore"],
        work=work,
        env=env,
        log=log,
    )
    _of(["patch", "--mission", "written mission"], work=work, env=env, log=log)
    home = work / ".orderfield"
    crash_env = dict(env)
    crash_env["OF_WAL_CRASH"] = "after-current"
    crashed = _run(
        ["of", "patch", "--mission", "crashed mission"],
        cwd=work,
        env=crash_env,
        timeout=90,
        log=log,
    )
    if crashed.returncode == 0 or "wal-crash" not in crashed.stderr:
        raise VerifyFailed(
            "verify-of: OF_WAL_CRASH=after-current did not crash the patch"
        )
    before = _mission(home / "ORDER.json")
    if before != "written mission":
        raise VerifyFailed(
            f"verify-of: live mission before resume is {before!r}, want 'written mission'"
        )
    resumed = _run(["of", "resume"], cwd=work, env=env, timeout=90, log=log)
    _require(resumed, ["of", "resume"])
    if "repaired live from CURRENT" not in resumed.stdout:
        raise VerifyFailed("verify-of: resume did not report repaired live from CURRENT")
    current = _json_object(home / "wal" / "CURRENT.json")
    materialized = _json_object(home / "wal" / "MATERIALIZED.json")
    generation = current.get("generation")
    if not isinstance(generation, str) or generation != materialized.get("generation"):
        raise VerifyFailed(
            "verify-of: MATERIALIZED generation "
            f"{materialized.get('generation')!r} != CURRENT {generation!r}"
        )
    files = current.get("files")
    if not isinstance(files, dict) or not files:
        raise VerifyFailed("verify-of: CURRENT has no files map")
    for rel in sorted(files):
        if not isinstance(rel, str) or Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise VerifyFailed(f"verify-of: CURRENT file path is not a field relative: {rel!r}")
        committed = home / "wal" / generation / rel
        live = home / rel
        if not committed.is_file() or not live.is_file():
            raise VerifyFailed(f"verify-of: missing live or CURRENT copy of {rel}")
        if live.read_bytes() != committed.read_bytes():
            raise VerifyFailed(f"verify-of: live {rel} != CURRENT generation")
    after = _mission(home / "ORDER.json")
    if after != "crashed mission":
        raise VerifyFailed(
            f"verify-of: live mission after resume is {after!r}, want 'crashed mission'"
        )
    return {
        "live_mission_after_crash": before,
        "live_mission_after_resume": after,
        "current_generation": generation,
        "materialized_generation": generation,
    }


def _drive_evidence_close(work: Path, env: dict[str, str], log: list[str]) -> dict[str, str]:
    """One close refused for a command-less done_when, then one close that binds the run."""
    _prepare_repo(work, env, log)
    _of(
        ["init", "--mission", "m", "--phase", "explore"],
        work=work,
        env=env,
        log=log,
    )
    _of(
        ["spec", "--add", "CLI-001", "--text", "the CLI prints a price table"],
        work=work,
        env=env,
        log=log,
    )
    proof = work / "surface.log"
    proof.write_text("$ price\nprice table\n", encoding="utf-8")
    log.append("$ write surface.log")
    log.append("")
    _of(
        ["spec", "--verified-contract", "CLI-001", "--cite", "surface.log"],
        work=work,
        env=env,
        log=log,
    )
    _of(
        ["patch", "--done-when-mission", "the price table is done"],
        work=work,
        env=env,
        log=log,
    )
    refused = _run(["of", "close"], cwd=work, env=env, timeout=90, log=log)
    if refused.returncode == 0 or "names no command" not in refused.stderr:
        raise VerifyFailed(
            "verify-of: close accepted a done_when that names no command"
        )
    if (work / ".orderfield" / "CLOSE.json").exists():
        raise VerifyFailed("verify-of: refused close wrote CLOSE.json")
    price = work / "price_cli.py"
    price.write_text('print("price table")\n', encoding="utf-8")
    log.append("$ write price_cli.py")
    log.append("")
    _of(
        [
            "patch",
            "--done-when-mission",
            "`python3 price_cli.py` prints a price table",
        ],
        work=work,
        env=env,
        log=log,
    )
    _of(["close"], work=work, env=env, log=log)
    return {
        "refused_done_when": "names no command",
        "accepted_command": "python3 price_cli.py",
    }


def _product_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if ".orderfield" in path.parts or ".git" in path.parts:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _drive_learn_checks(work: Path, env: dict[str, str], log: list[str]) -> dict[str, str]:
    """Two fields, one claim. Propose writes nothing. Accept writes the check."""
    _prepare_repo(work, env, log)
    _of(
        ["init", "--mission", "show a price table", "--phase", "explore"],
        work=work,
        env=env,
        log=log,
    )
    _of(
        ["new", "--mission", "show the price table again"],
        work=work,
        env=env,
        log=log,
    )
    homes = sorted((work / ".orderfield" / "fields").glob("ord_*"))
    if len(homes) != 2:
        raise VerifyFailed(f"verify-of: expected two fields, found {len(homes)}")
    body = {
        "status": "threshold",
        "result_ref": "notes.md",
        "residual": {
            "wants_to_change": ["constraints"],
            "evidence": "the price table is not in the contract",
            "proposed_patch": {"constraints+": ["price_cli.py prints price table"]},
        },
        "metrics": {
            "uncertainty": 0.2,
            "divergence": 0.2,
            "tool_failures": 0,
            "novelty": False,
        },
    }
    first = homes[0] / "waves" / "001" / "residuals" / "child.json"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text(json.dumps(body) + "\n", encoding="utf-8")
    log.append("$ write one residual")
    log.append(str(first.relative_to(work)))
    log.append("")
    alone = _run(["of", "learn", "--checks"], cwd=work, env=env, timeout=90, log=log)
    if alone.returncode != 0 or "none" not in alone.stdout:
        raise VerifyFailed("verify-of: one residual proposed a check")
    second_body = json.loads(json.dumps(body))
    second_body["residual"]["evidence"] = "different words, same missing constraint"
    second = homes[1] / "waves" / "001" / "residuals" / "child.json"
    second.parent.mkdir(parents=True, exist_ok=True)
    second.write_text(json.dumps(second_body) + "\n", encoding="utf-8")
    log.append("$ write the same claim in the other field")
    log.append(str(second.relative_to(work)))
    log.append("")
    before = _product_digest(work)
    proposed = _run(["of", "learn", "--checks"], cwd=work, env=env, timeout=90, log=log)
    if proposed.returncode != 0:
        raise VerifyFailed("verify-of: of learn --checks failed")
    if _product_digest(work) != before:
        raise VerifyFailed("verify-of: of learn --checks changed the repo")
    kinds = [line.split()[0] for line in proposed.stdout.splitlines() if line.strip()]
    if kinds != ["redesign", "check", "run", "prose"]:
        raise VerifyFailed(f"verify-of: proposal order is {kinds}")
    planted = json.loads(second.read_text(encoding="utf-8"))
    patch = planted["residual"]["proposed_patch"]
    if not patch.get("constraints+") and not patch.get("done_when+"):
        raise VerifyFailed("verify-of: redesign printed without constraints+ or done_when+")
    messages: dict[str, str] = {}
    for line in proposed.stdout.splitlines():
        if not line.strip():
            continue
        kind = line[:12].strip()
        _ident, rest = line[12:].lstrip().split("  ", 1)
        _fields, message = rest.split("  ", 1)
        messages[kind] = message
    if len(set(messages.values())) != 4:
        raise VerifyFailed(f"verify-of: proposal messages are not distinct: {messages}")
    if not messages["redesign"].startswith("fold into the plan: constraint "):
        raise VerifyFailed(f"verify-of: redesign does not name the contract: {messages['redesign']}")
    if "scripts/checks/" not in messages["check"] or " asserts FAIL " not in messages["check"]:
        raise VerifyFailed(f"verify-of: check does not name the script: {messages['check']}")
    if not messages["run"].startswith("feature-map row ") or "; done_when `" not in messages["run"]:
        raise VerifyFailed(f"verify-of: run does not name the row and command: {messages['run']}")
    if not messages["prose"].startswith("AGENTS.md: - "):
        raise VerifyFailed(f"verify-of: prose does not name the AGENTS.md line: {messages['prose']}")
    check_id = next(line.split()[1] for line in proposed.stdout.splitlines() if line.startswith("check"))
    key = check_id.split("_")[1]
    _of(["learn", "--accept", check_id], work=work, env=env, log=log)
    script = work / "scripts" / "checks" / f"{key}.py"
    if not script.is_file():
        raise VerifyFailed("verify-of: accept did not write the check")
    ran = _run([sys.executable, str(script)], cwd=work, env=env, timeout=30, log=log)
    if ran.returncode != 1:
        raise VerifyFailed("verify-of: the check passed before the fix")
    message = f"FAIL {key}: add constraint 'price_cli.py prints price table'"
    if message not in ran.stderr:
        raise VerifyFailed("verify-of: the check failure does not name the fix")
    status = _run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "scripts", "AGENTS.md"],
        cwd=work,
        env=env,
        timeout=30,
        log=log,
    )
    if status.returncode != 0 or f"scripts/checks/{key}.py" not in status.stdout:
        raise VerifyFailed("verify-of: git status did not show the accepted check")
    return {
        "proposal_order": "redesign check run prose",
        "redesign_gate": "constraints+",
        "redesign_message": messages["redesign"],
        "check_message": messages["check"],
        "run_message": messages["run"],
        "prose_message": messages["prose"],
        "script_failure": message,
        "repo_unchanged_until_accept": "true",
        "single_residual": "none",
    }


def _drive(feature: str, work: Path, env: dict[str, str], child: Path, log: list[str]) -> dict[str, str]:
    if feature == "wal-resume":
        return _drive_wal_resume(work, env, log)
    if feature == "evidence-close":
        return _drive_evidence_close(work, env, log)
    if feature == "plan-feature-map":
        return _drive_plan_feature_map(work, env, log)
    if feature == "learn-checks":
        return _drive_learn_checks(work, env, log)
    if feature == "local-metrics":
        return _drive_local_metrics(work, env, log)
    want = _through(feature)
    if "init-plan" not in want:
        return {}
    _prepare_repo(work, env, log)
    _of(
        [
            "init",
            "--mission",
            "decidable architecture for a pricing tool",
            "--phase",
            "explore",
            "--source",
            "the pricing tool must print a price table from the CLI",
        ],
        work=work,
        env=env,
        log=log,
    )
    _of(
        [
            "spec",
            "--add",
            "CLI-001",
            "--surface",
            "contract",
            "--text",
            "the CLI prints a price table",
        ],
        work=work,
        env=env,
        log=log,
    )
    if "pack-wave" not in want:
        return {}
    _of(
        [
            "pack",
            "--slice",
            "map pricing models, do not choose the phase",
            "--role",
            "explorer",
            "--child-id",
            "explorer",
            "--owns-requirement",
            "CLI-001",
        ],
        work=work,
        env=env,
        log=log,
    )
    if "collect-wave" not in want:
        return {}
    spawn_env = dict(env)
    spawn_env["OF_AGENT"] = f"{sys.executable} {shlex.quote(str(child))}"
    _of(
        [
            "spawn",
            "--adapter",
            "generic",
            "--packet",
            ".orderfield/waves/001/packets/explorer.json",
        ],
        work=work,
        env=spawn_env,
        log=log,
    )
    _of(["collect", "--wave", "1"], work=work, env=env, log=log)
    _of(["integrate", "--wave", "1"], work=work, env=env, log=log)
    if "close-field" not in want:
        return {}
    price = work / "price_cli.py"
    price.write_text('print("price table")\n', encoding="utf-8")
    log.append("$ write price_cli.py")
    log.append('# print("price table")')
    log.append("")
    _of(
        ["spec", "--verified-contract", "CLI-001", "--run", "python3 price_cli.py"],
        work=work,
        env=env,
        log=log,
    )
    _of(["contrast"], work=work, env=env, log=log)
    _of(["close", "--checklist"], work=work, env=env, log=log)
    _of(["close"], work=work, env=env, log=log)
    _of(["status"], work=work, env=env, log=log)
    _of(["resume"], work=work, env=env, log=log)
    return {}


def _drive_plan_feature_map(work: Path, env: dict[str, str], log: list[str]) -> dict[str, str]:
    """Init writes the map. One row is a real command. One row names what is missing."""
    _prepare_repo(work, env, log)
    price = work / "price_cli.py"
    price.write_text('print("price table")\n', encoding="utf-8")
    log.append("$ write price_cli.py")
    log.append('# print("price table")')
    log.append("")
    _of(
        [
            "init",
            "--mission",
            "prices `python3 price_cli.py` and `node gone.js`",
            "--phase",
            "explore",
        ],
        work=work,
        env=env,
        log=log,
    )
    home = work / ".orderfield"
    feature_map = (home / "feature-map.md").read_text(encoding="utf-8")
    log.append("$ read .orderfield/feature-map.md")
    log.append(feature_map.rstrip("\n"))
    log.append("")
    if "| price_cli.py | `python3 price_cli.py` | `python3 price_cli.py` |" not in feature_map:
        raise VerifyFailed("verify-of: feature map did not keep the runnable command")
    if "| gone.js | `node gone.js` | cannot run: gone.js is missing |" not in feature_map:
        raise VerifyFailed("verify-of: feature map invented evidence for a missing file")
    if "`cannot run:" in feature_map:
        raise VerifyFailed("verify-of: cannot-run row was given a command")
    order = _json_object(home / "ORDER.json")
    done = order.get("done_when")
    if done != ["`python3 price_cli.py`", "cannot run: gone.js is missing"]:
        raise VerifyFailed(f"verify-of: done_when was not derived from the map: {done!r}")
    _of(
        ["spec", "--add", "CLI-001", "--text", "the CLI prints a price table"],
        work=work,
        env=env,
        log=log,
    )
    proof = work / "surface.log"
    proof.write_text("$ price\nprice table\n", encoding="utf-8")
    log.append("$ write surface.log")
    log.append("")
    _of(
        ["spec", "--verified-contract", "CLI-001", "--cite", "surface.log"],
        work=work,
        env=env,
        log=log,
    )
    refused = _run(["of", "close"], cwd=work, env=env, timeout=90, log=log)
    if refused.returncode == 0 or "gone.js" not in refused.stderr:
        raise VerifyFailed("verify-of: close invented a receipt for a missing file")
    if (home / "CLOSE.json").exists():
        raise VerifyFailed("verify-of: refused close wrote CLOSE.json")
    return {
        "derived_command": "python3 price_cli.py",
        "missing": "gone.js",
    }


def _git_stamp(ts: int) -> str:
    return datetime.datetime.fromtimestamp(
        ts, datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%S+0000")


def _drive_local_metrics(work: Path, env: dict[str, str], log: list[str]) -> dict[str, str]:
    """Doctor on a repo with a real revert, then again with gh off PATH."""
    work.mkdir(parents=True, exist_ok=True)
    _require(
        _run(["git", "init", "-q"], cwd=work, env=env, timeout=30, log=log),
        ["git", "init", "-q"],
    )
    for argv in (
        ["git", "config", "user.email", "verify-of@example.invalid"],
        ["git", "config", "user.name", "verify-of"],
    ):
        _require(_run(argv, cwd=work, env=env, timeout=30, log=log), argv)
    recent = int(time.time())
    (work / "hello.txt").write_text("one\n", encoding="utf-8")
    log.append("$ write hello.txt")
    log.append("")
    _require(
        _run(["git", "add", "--", "hello.txt"], cwd=work, env=env, timeout=30, log=log),
        ["git", "add", "--", "hello.txt"],
    )
    _commit_at(work, env, log, "add", recent - 2 * 86400)
    (work / "more.txt").write_text("two\n", encoding="utf-8")
    log.append("$ write more.txt")
    log.append("")
    _require(
        _run(["git", "add", "--", "more.txt"], cwd=work, env=env, timeout=30, log=log),
        ["git", "add", "--", "more.txt"],
    )
    _commit_at(work, env, log, "more", recent - 86400)
    _commit_at(work, env, log, None, recent - 3600, revert=True)
    measured = _run(["of", "doctor"], cwd=work, env=env, timeout=90, log=log)
    _require(measured, ["of", "doctor"])
    _doctor_ok(measured.stdout)
    for needle in (
        "revert        1/3  33.3%",
        "rewrite       1/2  50.0%",
        "within 14 days",
    ):
        if needle not in measured.stdout:
            raise VerifyFailed(f"verify-of: doctor repo block missing {needle!r}")
    private = work / "nogh-bin"
    private.mkdir()
    for name in ("git", "python3"):
        src = shutil.which(name)
        if not src:
            raise VerifyFailed(f"verify-of: {name} is not on PATH")
        os.symlink(src, private / name)
    absent = dict(env)
    bindir = env["PATH"].split(os.pathsep, 1)[0]
    absent["PATH"] = bindir + os.pathsep + str(private)
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GH_HOST"):
        absent.pop(key, None)
    skipped = _run(["of", "doctor"], cwd=work, env=absent, timeout=90, log=log)
    _require(skipped, ["of", "doctor"])
    _doctor_ok(skipped.stdout)
    sentence = "PR data was skipped (gh is not installed)"
    if sentence not in skipped.stdout:
        raise VerifyFailed("verify-of: gh-absent doctor did not skip PR data")
    if "revert        1/3  33.3%" not in skipped.stdout:
        raise VerifyFailed("verify-of: gh-absent doctor lost the revert count")
    return {
        "revert": "1/3",
        "rewrite": "1/2",
        "pr_absent": sentence,
    }


def _commit_at(
    work: Path,
    env: dict[str, str],
    log: list[str],
    message: str | None,
    ts: int,
    *,
    revert: bool = False,
) -> None:
    dated = dict(env)
    stamp = _git_stamp(ts)
    dated["GIT_AUTHOR_DATE"] = stamp
    dated["GIT_COMMITTER_DATE"] = stamp
    dated["GIT_EDITOR"] = "true"
    if revert:
        argv = ["git", "revert", "--no-edit", "HEAD"]
    else:
        argv = ["git", "commit", "-q", "-m", message or "commit"]
    _require(_run(argv, cwd=work, env=dated, timeout=30, log=log), argv)


def _write_evidence(
    dest: Path,
    *,
    feature: str,
    version: str,
    log: list[str],
    doctor_text: str,
    close_path: Path | None,
    extra: dict[str, str] | None = None,
    copies: list[tuple[str, Path]] | None = None,
) -> None:
    dest.mkdir(parents=True, exist_ok=False)
    transcript = "\n".join(log).rstrip() + "\n"
    (dest / "transcript.txt").write_text(transcript, encoding="utf-8")
    (dest / "doctor.txt").write_text(doctor_text, encoding="utf-8")
    copied: list[str] = []
    for name, src in copies or []:
        if not src.is_file():
            raise VerifyFailed(f"verify-of: missing evidence file {src}")
        shutil.copyfile(src, dest / name)
        copied.append(name)
    if close_path is not None:
        shutil.copyfile(close_path, dest / "CLOSE.json")
    manifest = {
        "feature": feature,
        "version": version,
        "doctor": "ok",
        "files": ["transcript.txt", "doctor.txt"]
        + copied
        + (["CLOSE.json"] if close_path is not None else []),
    }
    if extra:
        manifest.update(extra)
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def _remove(path: Path | None) -> None:
    if path is None or not path.exists():
        return
    resolved = path.resolve()
    if resolved == ROOT.resolve() or ROOT.resolve() in resolved.parents:
        raise VerifyFailed(f"verify-of: refusing to delete a checkout path: {resolved}")
    shutil.rmtree(resolved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drive one real of feature and keep the evidence.")
    parser.add_argument("--feature", required=True, choices=FEATURES)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    run_id = args.run_id.strip() or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if args.evidence_dir is not None:
        evidence = args.evidence_dir
    else:
        evidence = DEFAULT_EVIDENCE_ROOT / run_id
    evidence = evidence.resolve()
    if evidence.exists():
        raise VerifyFailed(f"verify-of: evidence dir already exists: {evidence}")

    scratch = Path(tempfile.mkdtemp(prefix="verify-of-home-"))
    work: Path | None = None
    log: list[str] = []
    failed: BaseException | None = None
    try:
        (scratch / "tmp").mkdir()
        env = _base_env(scratch)
        install_argv = ["bash", str(INSTALL), "--root", str(scratch)]
        _require(
            _run(install_argv, cwd=ROOT, env=env, timeout=120, log=log),
            install_argv,
        )
        of_bin = scratch / ".local" / "bin" / "of"
        if not of_bin.is_symlink():
            raise VerifyFailed(f"verify-of: installed of symlink missing: {of_bin}")
        doctor_cwd = scratch / "doctor-cwd"
        doctor_cwd.mkdir()
        doctor = _run(["of", "doctor"], cwd=doctor_cwd, env=env, timeout=60, log=log)
        _require(doctor, ["of", "doctor"])
        _doctor_ok(doctor.stdout)
        expected = VERSION_FILE.read_text(encoding="utf-8").strip()
        found = _kernel_version(doctor.stdout)
        if found != expected:
            raise VerifyFailed(
                f"verify-of: doctor kernel {found} != VERSION {expected}"
            )
        child = scratch / "verify_child.py"
        child.write_text(CHILD, encoding="utf-8")
        child.chmod(0o755)
        close_path: Path | None = None
        extra: dict[str, str] = {}
        copies: list[tuple[str, Path]] = []
        if args.feature != "doctor":
            work = Path(tempfile.mkdtemp(prefix="verify-of-repo-"))
            extra = _drive(args.feature, work, env, child, log)
            if args.feature in {"close-field", "evidence-close"}:
                close_path = work / ".orderfield" / "CLOSE.json"
                if not close_path.is_file():
                    raise VerifyFailed("verify-of: close did not write CLOSE.json")
                proof = json.loads(close_path.read_text(encoding="utf-8"))
                if not isinstance(proof, dict) or "requirements" not in proof:
                    raise VerifyFailed("verify-of: CLOSE.json is not a close proof")
                if args.feature == "evidence-close":
                    rows = proof.get("done_when")
                    if not isinstance(rows, list) or not rows:
                        raise VerifyFailed("verify-of: CLOSE.json done_when is empty")
                    row = rows[0]
                    if not isinstance(row, dict):
                        raise VerifyFailed("verify-of: CLOSE.json done_when row is not an object")
                    if row.get("command") != "python3 price_cli.py":
                        raise VerifyFailed(
                            f"verify-of: done_when command is {row.get('command')!r}"
                        )
                    if "price table" not in str(row.get("output") or ""):
                        raise VerifyFailed("verify-of: done_when output lacks the command output")
            if args.feature == "plan-feature-map" and work is not None:
                copies = [
                    ("feature-map.md", work / ".orderfield" / "feature-map.md"),
                    ("ORDER.json", work / ".orderfield" / "ORDER.json"),
                ]
            if args.feature == "learn-checks" and work is not None:
                scripts = sorted((work / "scripts" / "checks").glob("*.py"))
                if len(scripts) != 1:
                    raise VerifyFailed(f"verify-of: expected one check script, found {len(scripts)}")
                copies = [("check.py", scripts[0])]
        _write_evidence(
            evidence,
            feature=args.feature,
            version=expected,
            log=log,
            doctor_text=doctor.stdout,
            close_path=close_path,
            extra=extra,
            copies=copies,
        )
    except Exception as exc:
        failed = exc
    finally:
        _remove(work)
        _remove(scratch)
    if failed is not None:
        text = "\n".join(log).rstrip()
        if text:
            print(text, file=sys.stderr)
        if isinstance(failed, subprocess.TimeoutExpired):
            raise VerifyFailed(f"verify-of: timed out: {failed}") from failed
        raise failed

    missing = [name for name in ("transcript.txt", "doctor.txt", "manifest.json") if not (evidence / name).is_file()]
    if args.feature in {"close-field", "evidence-close"} and not (evidence / "CLOSE.json").is_file():
        missing.append("CLOSE.json")
    if args.feature == "plan-feature-map":
        for name in ("feature-map.md", "ORDER.json"):
            if not (evidence / name).is_file():
                missing.append(name)
    if args.feature == "learn-checks" and not (evidence / "check.py").is_file():
        missing.append("check.py")
    if missing or scratch.exists() or (work is not None and work.exists()):
        raise VerifyFailed(
            "verify-of: evidence did not survive cleanup "
            f"(missing={missing}, scratch_gone={not scratch.exists()})"
        )
    manifest_path = evidence / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence_survived_cleanup"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"evidence {evidence}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except VerifyFailed as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
