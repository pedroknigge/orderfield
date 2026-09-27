#!/usr/bin/env python3
"""Cherry-picked dogfood hardening (no arena): kernel sha + pins,
field-scoped residual paths, close fallback notes, deliverables,
done-when seeding for analysis fields.

Source: cursor/campo-runtime-tracer-af96 (dogfood audit, tokky-broker-web).
The Campo election/quorum/roster machinery was deliberately NOT ported:
selection by the field (of contrast), not by debate.
"""
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
OF_PY = SCRIPTS / "of.py"


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


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-picks-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)


class SpawnDryRunPath(_Base):
    def test_dry_run_residual_is_field_scoped(self) -> None:
        self.assertEqual(run_of(self.tmp, "init", "--mission", "first", "--phase", "explore").returncode, 0)
        new = run_of(self.tmp, "new", "--mission", "second field", "--phase", "explore")
        self.assertEqual(new.returncode, 0, new.stdout + new.stderr)
        pack = run_of(self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "d1")
        self.assertEqual(pack.returncode, 0, pack.stdout + pack.stderr)
        packet = pack.stdout.splitlines()[0].strip()
        spawn = run_of(self.tmp, "spawn", "--adapter", "claude", "--packet", packet, "--dry-run")
        self.assertEqual(spawn.returncode, 0, spawn.stderr)
        lines = [line for line in spawn.stdout.splitlines() if line.startswith("residual=")]
        self.assertTrue(lines, spawn.stdout)
        self.assertIn(".orderfield/fields/", lines[0])
        self.assertNotIn("residual=.orderfield/waves/", spawn.stdout)


class CloseFallbackAndStub(_Base):
    def _fields(self, docs: dict[str, dict]) -> Path:
        of_dir = self.tmp / ".orderfield"
        for fid, doc in docs.items():
            home = of_dir / "fields" / fid
            home.mkdir(parents=True, exist_ok=True)
            (home / "ORDER.json").write_text(json.dumps({"id": fid, **doc}) + "\n")
        return of_dir

    def test_close_warns_when_active_falls_back(self) -> None:
        from of.field import ActiveField

        of_dir = self._fields({
            "ord_11111111": {"mission": "stale epic", "spec_closed": False},
            "ord_22222222": {"mission": "fresh analysis", "spec_closed": True},
        })
        (of_dir / "ACTIVE").write_text("ord_22222222\n")
        ActiveField.release_closed(self.tmp, "ord_22222222")
        self.assertEqual(ActiveField.read(self.tmp), "ord_11111111")
        note = ActiveField.fallback_note(self.tmp, "ord_22222222")
        self.assertIn("fell back to open field ord_11111111", note)
        self.assertIn("stale epic", note)
        self.assertIn("Leader: ask the user", note)
        self.assertIn("of gc --archive-field ord_11111111", note)

    def test_close_names_several_open_fields(self) -> None:
        from of.field import ActiveField

        self._fields({
            "ord_11111111": {"mission": "a", "spec_closed": False},
            "ord_33333333": {"mission": "b", "spec_closed": False},
            "ord_22222222": {"mission": "c", "spec_closed": True},
        })
        note = ActiveField.fallback_note(self.tmp, "ord_22222222")
        self.assertIn("active      unset; 2 open fields", note)

    def test_close_wires_fallback_note(self) -> None:
        src = (SCRIPTS / "of" / "cli" / "spec_cmd.py").read_text()
        self.assertIn("ActiveField.fallback_note(root", src)

    def _stub_after_fields(self, doc: dict) -> tuple[Path, str]:
        import contextlib
        import io

        from of.field import promote_legacy_layout

        of_dir = self.tmp / ".orderfield"
        (of_dir / "fields" / "ord_aaaaaaaa").mkdir(parents=True)
        (of_dir / "fields" / "ord_aaaaaaaa" / "ORDER.json").write_text(
            json.dumps({"id": "ord_aaaaaaaa", "mission": "live"}) + "\n"
        )
        stub = of_dir / "ORDER.json"
        stub.write_text(json.dumps(doc) + "\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            promote_legacy_layout(self.tmp)
        return stub, buf.getvalue()

    def test_closed_root_stub_auto_archived(self) -> None:
        stub, out = self._stub_after_fields(
            {"id": "ord_deadbeef", "spec_closed": True, "mission": "old"}
        )
        self.assertIn("archived closed leftover", out)
        self.assertFalse(stub.exists())
        self.assertTrue((stub.parent / "ORDER.json.stub").is_file())
        self.assertNotIn("ambiguous", out)

    def test_open_root_stub_explained_to_leader(self) -> None:
        stub, out = self._stub_after_fields({"id": "ord_deadbeef", "mission": "old"})
        self.assertTrue(stub.exists(), "open stub never deleted")
        self.assertIn("ambiguous", out)
        self.assertIn("Leader: ask the user whether it is still live", out)


class DoneWhenSeedTest(unittest.TestCase):
    def test_seed_only_for_empty_explore(self) -> None:
        from of.cli.init_cmd import DoneWhenSeed

        seeded = DoneWhenSeed.requirements([], "explore", ["analysis report written"])
        self.assertEqual(seeded[0]["id"], "DONE-001")
        self.assertTrue(seeded[0]["binding"])
        self.assertEqual(seeded[0]["origin"], "added")
        self.assertEqual(DoneWhenSeed.requirements([{"id": "X-001"}], "explore", ["x"]), [])
        self.assertEqual(DoneWhenSeed.requirements([], "build", ["x"]), [])
        self.assertEqual(DoneWhenSeed.requirements([], "explore", None), [])


class DoneWhenSeedCli(_Base):
    def test_explore_init_seeds_done_requirement(self) -> None:
        proc = run_of(
            self.tmp, "init", "--mission", "analyze the project", "--phase", "explore",
            "--source", "analiza este proyecto y propone mejoras",
            "--done-when", "improvement report written",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("seeded from --done-when", proc.stdout)
        req = json.loads(next((self.tmp / ".orderfield").rglob("REQUIREMENTS.json")).read_text())
        ids = [r["id"] for r in req["requirements"]]
        self.assertEqual(ids, ["DONE-001"])
        spec = next((self.tmp / ".orderfield").rglob("SPEC.md")).read_text()
        self.assertIn("analiza este proyecto", spec)
        self.assertNotIn("DONE-001", spec)


class DeliverableClose(_Base):
    def test_promote_copies_final_before_wipe(self) -> None:
        from of.retain import Deliverable

        home = self.tmp / ".orderfield" / "fields" / "ord_aaaaaaaa"
        scratch = home / "work" / "scratch"
        (scratch / "leader").mkdir(parents=True)
        (scratch / "leader" / "FINAL.md").write_text("# Final\n", encoding="utf-8")
        (scratch / "leader" / "notes.md").write_text("n\n", encoding="utf-8")
        done = Deliverable.promote(self.tmp, home)
        self.assertTrue((home / "FINAL.md").is_file())
        self.assertTrue((home / "deliverables" / "leader" / "notes.md").is_file())
        self.assertTrue(done)


if __name__ == "__main__":
    unittest.main()
