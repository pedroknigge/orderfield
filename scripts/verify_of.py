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
FEATURES = ("doctor", "init-plan", "pack-wave", "collect-wave", "close-field")

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
    if feature not in FEATURES:
        raise VerifyFailed(f"verify-of: unknown feature {feature}")
    index = FEATURES.index(feature)
    return set(FEATURES[: index + 1])


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


def _drive(feature: str, work: Path, env: dict[str, str], child: Path, log: list[str]) -> None:
    want = _through(feature)
    if "init-plan" not in want:
        return
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
        return
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
        return
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
        return
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


def _write_evidence(
    dest: Path,
    *,
    feature: str,
    version: str,
    log: list[str],
    doctor_text: str,
    close_path: Path | None,
) -> None:
    dest.mkdir(parents=True, exist_ok=False)
    transcript = "\n".join(log).rstrip() + "\n"
    (dest / "transcript.txt").write_text(transcript, encoding="utf-8")
    (dest / "doctor.txt").write_text(doctor_text, encoding="utf-8")
    if close_path is not None:
        shutil.copyfile(close_path, dest / "CLOSE.json")
    manifest = {
        "feature": feature,
        "version": version,
        "doctor": "ok",
        "files": ["transcript.txt", "doctor.txt"]
        + (["CLOSE.json"] if close_path is not None else []),
    }
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
        if args.feature != "doctor":
            work = Path(tempfile.mkdtemp(prefix="verify-of-repo-"))
            _drive(args.feature, work, env, child, log)
            if args.feature == "close-field":
                close_path = work / ".orderfield" / "CLOSE.json"
                if not close_path.is_file():
                    raise VerifyFailed("verify-of: close did not write CLOSE.json")
                proof = json.loads(close_path.read_text(encoding="utf-8"))
                if not isinstance(proof, dict) or "requirements" not in proof:
                    raise VerifyFailed("verify-of: CLOSE.json is not a close proof")
        _write_evidence(
            evidence,
            feature=args.feature,
            version=expected,
            log=log,
            doctor_text=doctor.stdout,
            close_path=close_path,
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
    if args.feature == "close-field" and not (evidence / "CLOSE.json").is_file():
        missing.append("CLOSE.json")
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
