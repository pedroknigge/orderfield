#!/usr/bin/env python3
"""CLI/file surface for LOOP-001, DEDUPE-001, PHASE-001, BACKLOG-001."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402

OF_PY = SCRIPTS / "of.py"
DONE = ROOT / "assets" / "fixtures" / "residual.done.json"


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_path(root: Path, child_id: str, wave: int = 1) -> Path:
    return (
        root
        / ".orderfield"
        / "waves"
        / f"{wave:03d}"
        / "packets"
        / f"{child_id}.json"
    )


def write_bound_residual(
    root: Path,
    child_id: str,
    *,
    patch: dict | None = None,
    wave: int = 1,
) -> Path:
    packet = load_json(packet_path(root, child_id, wave))
    residual = load_json(DONE)
    for key in of.PACKET_IDENTITY_FIELDS:
        residual[key] = packet[key]
    result = root / ".orderfield" / "work" / "scratch" / child_id / "result.md"
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text("LOOP-001 done residual; CLI collect/integrate.\n", encoding="utf-8")
    residual["result_ref"] = result.relative_to(root).as_posix()
    residual["residual"]["evidence"] = (
        "LOOP-001 collect and integrate print owned-but-unverified; "
        "never auto-stamp verified_contract."
    )
    if patch is not None:
        residual["residual"]["proposed_patch"] = patch
    destination = root / str(packet["residual_path"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
    return destination


def req_status(root: Path, req_id: str) -> str:
    data = load_json(root / ".orderfield" / "REQUIREMENTS.json")
    for item in data.get("requirements") or []:
        if item.get("id") == req_id:
            return str(item.get("status") or "")
    raise AssertionError(f"missing requirement {req_id}")


class Loop001CollectIntegrate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-loop-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "spec",
            "--add",
            "LOOP-001",
            "--text",
            "collect and integrate print owned-but-unverified; never auto-stamp",
            "--surface",
            "contract",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(
            self.tmp,
            "pack",
            "--slice",
            "loop",
            "--role",
            "implementer",
            "--child-id",
            "c1",
            "--owns-requirement",
            "LOOP-001",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        write_bound_residual(
            self.tmp,
            "c1",
            patch={
                "requirements_verified": ["LOOP-001"],
                "requirements_verified_contract": ["LOOP-001"],
            },
        )

    def test_collect_prints_owned_but_unverified_after_done_residual(self) -> None:
        collected = run_of(self.tmp, "collect")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        self.assertIn("owned-but-unverified LOOP-001", collected.stdout)
        self.assertEqual(req_status(self.tmp, "LOOP-001"), "owned")

    def test_integrate_prints_and_does_not_auto_stamp_contract(self) -> None:
        integrated = run_of(self.tmp, "integrate", "--wave", "1", "--apply")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        json.loads(integrated.stdout)
        self.assertIn("owned-but-unverified LOOP-001", integrated.stderr)
        self.assertEqual(req_status(self.tmp, "LOOP-001"), "owned")
        stamped = run_of(self.tmp, "spec", "--verified-contract", "LOOP-001")
        self.assertEqual(stamped.returncode, 0, stamped.stderr)
        self.assertEqual(req_status(self.tmp, "LOOP-001"), "verified_contract")
        collected = run_of(self.tmp, "collect")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        self.assertNotIn("owned-but-unverified LOOP-001", collected.stdout)
        self.assertIn("owned-but-unverified", collected.stdout)


class IntegrateStdoutIsJson(unittest.TestCase):
    """#57 — successful integrate stdout is one JSON object; human notes go to stderr."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-int-json-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "mission residual",
            "--role",
            "implementer",
            "--child-id",
            "m1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        dest = write_bound_residual(
            self.tmp,
            "m1",
            patch={"mission": "do not auto-apply this"},
        )
        residual = load_json(dest)
        residual["residual"]["wants_to_change"] = ["mission"]
        dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")

    def _assert_stdout_json(self, proc: subprocess.CompletedProcess[str]) -> dict:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertIsInstance(report, dict)
        self.assertTrue(str(report.get("regime") or "").strip())
        self.assertNotIn("mission proposed_patch", proc.stdout)
        self.assertNotIn("not auto-applied", proc.stdout)
        self.assertNotIn("owned-but-unverified", proc.stdout)
        return report

    def test_apply_and_replay_stdout_are_json(self) -> None:
        applied = run_of(self.tmp, "integrate", "--wave", "1", "--apply")
        report = self._assert_stdout_json(applied)
        self.assertIn("mission proposed_patch is not auto-applied", applied.stderr)
        self.assertIn("of patch --mission", applied.stderr)
        replay = run_of(self.tmp, "integrate", "--wave", "1", "--apply")
        replayed = self._assert_stdout_json(replay)
        self.assertEqual(replayed["regime"], report["regime"])
        self.assertEqual(
            replayed["integration"]["input_hash"],
            report["integration"]["input_hash"],
        )
        as_json = run_of(self.tmp, "--json", "integrate", "--wave", "1", "--apply")
        self._assert_stdout_json(as_json)
        for line in as_json.stderr.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            self.assertIsInstance(event, dict, line)


class Dedupe001Constraints(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-dedupe-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _constraints(self) -> list:
        return load_json(self.tmp / ".orderfield" / "ORDER.json")["constraints"]

    def test_constraints_add_skips_whitespace_normalized_duplicate(self) -> None:
        r = run_of(self.tmp, "patch", "--constraints-add", "keep the contract kernel")
        self.assertEqual(r.returncode, 0, r.stderr)
        skipped = run_of(
            self.tmp, "patch", "--constraints-add", "  keep   the contract kernel  "
        )
        self.assertNotEqual(skipped.returncode, 0)
        self.assertIn("nothing to patch", skipped.stderr)
        self.assertEqual(
            self._constraints().count("keep the contract kernel"), 1
        )
        self.assertNotIn("  keep   the contract kernel  ", self._constraints())

    def test_apply_patches_skips_whitespace_normalized_constraints(self) -> None:
        r = run_of(
            self.tmp, "pack", "--slice", "d", "--role", "implementer", "--child-id", "d1"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        write_bound_residual(
            self.tmp,
            "d1",
            patch={"constraints+": ["slaves   do not mutate ORDER"]},
        )
        before = list(self._constraints())
        integrated = run_of(self.tmp, "integrate", "--wave", "1", "--apply")
        self.assertEqual(integrated.returncode, 0, integrated.stderr)
        self.assertEqual(self._constraints(), before)


class Phase001PhaseMd(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-phase-md-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_phase_md_splits_mission_and_phase_lists(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "cut theater",
            "--phase",
            "build",
            "--done-when",
            "tests green",
            "--done-when",
            "build: land the kernel",
            "--done-when",
            "explore: map it",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        path = self.tmp / ".orderfield" / "PHASE.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("done_when_mission:", text)
        self.assertIn("done_when_phase:", text)
        self.assertIn("- tests green", text)
        self.assertIn("- build: land the kernel", text)
        self.assertNotIn("explore: map it", text)
        self.assertNotIn("Done when:", text)

    def test_empty_lists_print_one_line_and_keep_file(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        order["done_when"] = []
        of.write_phase_md(self.tmp, order)
        path = self.tmp / ".orderfield" / "PHASE.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("no phase criteria; of patch --done-when", text)
        self.assertNotIn("done_when_mission:", text)
        self.assertNotIn("done_when_phase:", text)


class Backlog001Undone(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-backlog-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m", "--phase", "build")
        self.assertEqual(r.returncode, 0, r.stderr)
        for step in ("step one", "step two", "step three"):
            r = run_of(self.tmp, "patch", "--backlog-add", step)
            self.assertEqual(r.returncode, 0, r.stderr)

    def _backlog(self) -> list:
        return load_json(self.tmp / ".orderfield" / "ORDER.json").get("backlog") or []

    def test_done_then_undone_restores_open_step_without_ghost_row(self) -> None:
        r = run_of(self.tmp, "patch", "--backlog-done", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(of.open_backlog(self._order()), ["step one", "step three"])
        r = run_of(self.tmp, "patch", "--backlog-undone", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        backlog = self._backlog()
        self.assertEqual(len(backlog), 3)
        self.assertEqual([b["text"] for b in backlog], ["step one", "step two", "step three"])
        self.assertFalse(backlog[1]["done"])
        self.assertEqual(of.open_backlog(self._order()), ["step one", "step two", "step three"])
        texts = " ".join(b["text"] for b in backlog)
        self.assertNotIn("REABIERTO", texts)
        self.assertEqual(len(backlog), 3)

    def test_undone_out_of_range_dies(self) -> None:
        r = run_of(self.tmp, "patch", "--backlog-undone", "7")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("out of range", r.stderr)

    def _order(self) -> dict:
        return load_json(self.tmp / ".orderfield" / "ORDER.json")


if __name__ == "__main__":
    unittest.main()
