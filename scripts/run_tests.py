#!/usr/bin/env python3
"""Stdlib parallel test runner. CI script, not a kernel package.

Runs every ``tests/test_*.py`` module in its own ``python -m unittest``
subprocess (cwd = repo root, so ``tests.<mod>`` imports resolve), up to
``--jobs`` at a time with a per-module ``--timeout``. Prints the slowest
modules and every failing test name; exits nonzero on any failure,
error, or timeout. Same tests as ``python3 -m unittest discover -s tests``,
only wall-clock differs: modules are subprocess-bound, not CPU-bound.
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
_FAILED_RE = re.compile(r"^(FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)
_RAN_RE = re.compile(r"^Ran (\d+) tests? in", re.M)


def discover(names: list[str]) -> list[str]:
    mods = sorted(p.stem for p in TESTS.glob("test_*.py"))
    if names:
        wanted = {n.removeprefix("tests.").removesuffix(".py") for n in names}
        missing = wanted - set(mods)
        if missing:
            raise SystemExit(f"run_tests: no such module(s): {', '.join(sorted(missing))}")
        mods = [m for m in mods if m in wanted]
    # Big files first: a long module started last sets the wall clock.
    return sorted(mods, key=lambda m: -(TESTS / f"{m}.py").stat().st_size)


def _is_loader_shim(mod: str) -> bool:
    """A module whose load_tests deliberately runs nothing (name loader only)."""
    return "\ndef load_tests(" in (TESTS / f"{mod}.py").read_text(encoding="utf-8")


def run_module(mod: str, timeout: float) -> dict:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    start = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, "-m", "unittest", "-v", f"tests.{mod}"],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # the module's CLI children too
        except ProcessLookupError:
            pass
        out, _ = proc.communicate()
    ran = _RAN_RE.search(out or "")
    failed = [f"{kind}: {where}" for kind, _name, where in _FAILED_RE.findall(out or "")]
    if timed_out:
        failed.append(f"TIMEOUT: tests.{mod} after {timeout:.0f}s")
    elif proc.returncode == 5 and not failed and _is_loader_shim(mod):
        pass  # 3.12+: "NO TESTS RAN" from a load_tests shim (test_kernel) is not a failure
    elif proc.returncode != 0 and not failed:
        failed.append(f"EXIT {proc.returncode}: tests.{mod}")
    return {
        "mod": mod, "secs": time.monotonic() - start, "ok": not failed,
        "ran": int(ran.group(1)) if ran else 0, "failed": failed, "out": out or "",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("modules", nargs="*", help="limit to these modules (test_x or tests.test_x)")
    ap.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--timeout", type=float, default=900.0, help="per-module seconds (default 900)")
    ap.add_argument("--top", type=int, default=20, help="slowest modules to print (default 20)")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every module's output")
    args = ap.parse_args(argv)

    mods = discover(args.modules)
    print(f"run_tests: {len(mods)} modules, jobs={args.jobs}, timeout={args.timeout:.0f}s", flush=True)
    t0 = time.monotonic()
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_module, m, args.timeout) for m in mods]
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            mark = "ok  " if r["ok"] else "FAIL"
            print(f"{mark} {r['secs']:7.1f}s  {r['ran']:4d} tests  tests.{r['mod']}", flush=True)
            if args.verbose:
                print(r["out"].rstrip() + "\n", flush=True)
            elif not r["ok"]:  # the failure blocks, not every passing test line
                cut = r["out"].find("\n" + "=" * 70)
                print((r["out"][cut:] if cut >= 0 else r["out"][-4000:]).rstrip() + "\n", flush=True)
    wall = time.monotonic() - t0

    print(f"\nslowest {min(args.top, len(results))} modules:")
    for r in sorted(results, key=lambda r: -r["secs"])[: args.top]:
        print(f"  {r['secs']:7.1f}s  tests.{r['mod']}")
    failed = [f for r in results for f in r["failed"]]
    total = sum(r["ran"] for r in results)
    serial = sum(r["secs"] for r in results)
    print(f"\n{total} tests in {len(results)} modules: wall {wall:.1f}s (module sum {serial:.1f}s)")
    if failed:
        print(f"\n{len(failed)} failing:")
        for f in failed:
            print(f"  {f}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
