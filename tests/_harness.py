"""Shared hermetic CLI runner for new tests (not collected: no test_ prefix).

`run_of` drives the shipped `scripts/of.py` with HOME, XDG_CACHE_HOME,
OF_LEARNINGS and TMPDIR pointed into one per-process sandbox, the update
check off, PATH cut to python + git, and every OF_* / harness-detection
variable from the caller's shell stripped, so a test sees only the env it
passes. Older modules keep
their own runners; do not refactor them onto this one.
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OF_PY = ROOT / "scripts" / "of.py"

# Caller-shell variables that change kernel behavior or harness detection.
_STRIP_PREFIXES = ("OF_", "ORDERFIELD_", "CODEX_", "CURSOR_", "CLAUDE", "OPENCODE", "GROK_", "QWEN_", "ORCA_", "AGY_")
# python + git + the system dirs only: real harness CLIs on the developer's
# PATH (claude, codex, agent, opencode, ...) are never probed or spawned.
_PATH = os.pathsep.join(dict.fromkeys(
    [str(Path(os.path.realpath(sys.executable)).parent)]
    + [str(Path(os.path.realpath(g)).parent) for g in [shutil.which("git")] if g]
    + ["/usr/bin", "/bin"]
))
_SANDBOX: Path | None = None
_LOCK = threading.Lock()


def sandbox() -> Path:
    """One HOME/TMPDIR/cache sandbox per test process, removed at exit."""
    global _SANDBOX
    with _LOCK:  # tests may drive several fields from threads
        if _SANDBOX is None:
            box = Path(tempfile.mkdtemp(prefix="of-harness-"))
            for sub in ("home", "cache", "tmp"):
                (box / sub).mkdir()
            atexit.register(shutil.rmtree, box, True)
            _SANDBOX = box
    return _SANDBOX


def hermetic_env(env: dict[str, str] | None = None) -> dict[str, str]:
    box = sandbox()
    full = {k: v for k, v in os.environ.items() if not k.startswith(_STRIP_PREFIXES)}
    full.update({
        "PATH": _PATH,
        "HOME": str(box / "home"),
        "XDG_CACHE_HOME": str(box / "cache"),
        "TMPDIR": str(box / "tmp"),
        "OF_LEARNINGS": str(box / "learnings.json"),
        "OF_SPAWN_REGISTRY": str(box / "spawn-registry.json"),
        "OF_NO_UPDATE_CHECK": "1",
        "OF_NO_GC_AUTO": "1",
    })
    full.update(env or {})
    return full


def run_of(cwd: Path, *args: str, env: dict[str, str] | None = None,
           timeout: float = 60) -> subprocess.CompletedProcess[str]:
    """Run `of <args>` in `cwd`; `env` overlays the hermetic base."""
    return subprocess.run(
        [sys.executable, str(OF_PY), *args], cwd=str(cwd), capture_output=True,
        text=True, env=hermetic_env(env), timeout=timeout,
    )


def popen_of(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.Popen:
    """Same env as `run_of`, for tests that signal the process mid-command."""
    return subprocess.Popen(
        [sys.executable, str(OF_PY), *args], cwd=str(cwd), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, env=hermetic_env(env),
    )
