#!/usr/bin/env python3
"""WAL-001 — CURRENT is the only reader view; crash both sides at CLI/file."""
from __future__ import annotations

import hashlib
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


def run_of(
    cwd: Path, *args: str, env_extra: dict | None = None
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", **(env_extra or {})}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    env.pop("OF_WAL_CRASH", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spawned_line(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("spawned"):
            return line
    return ""


class FieldWalBothSides(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-wal-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "wal mission", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.home = self.tmp / ".orderfield"
        self.wal = self.home / "wal"

    def pack(self, child: str, slice_text: str = "s", **env: str) -> subprocess.CompletedProcess[str]:
        extra = {"OF_WAL_CRASH": env["OF_WAL_CRASH"]} if "OF_WAL_CRASH" in env else None
        return run_of(
            self.tmp,
            "pack",
            "--slice",
            slice_text,
            "--role",
            "explorer",
            "--child-id",
            child,
            env_extra=extra,
        )

    def test_success_publish_writes_manifest_and_current(self) -> None:
        packed = self.pack("e1")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        current_path = self.wal / "CURRENT.json"
        self.assertTrue(current_path.is_file(), "publish pointer missing after pack")
        current = json.loads(current_path.read_text(encoding="utf-8"))
        gid = current["generation"]
        man_path = self.wal / gid / "MANIFEST.json"
        self.assertTrue(man_path.is_file(), man_path)
        man = json.loads(man_path.read_text(encoding="utf-8"))
        self.assertTrue(man.get("complete"))
        self.assertEqual(man["generation"], gid)
        files = man["files"]
        self.assertIn("state.json", files)
        self.assertIn("session.json", files)
        self.assertIn("ORDER.json", files)
        self.assertIn("PHASE.md", files)
        if (self.home / "SPEC.md").is_file():
            self.assertIn("SPEC.md", files)
        self.assertIn("waves/001/packets/e1.json", files)
        self.assertIn("waves/001/prompts/e1.md", files)
        for rel, digest in files.items():
            live = self.home / rel
            self.assertTrue(live.is_file(), rel)
            self.assertEqual(sha256_file(live), digest, rel)
            staged = self.wal / gid / rel
            self.assertTrue(staged.is_file(), staged)
            self.assertEqual(sha256_file(staged), digest)
        packet = json.loads((self.home / "waves/001/packets/e1.json").read_text())
        self.assertEqual(packet["budget"]["tokens"], 0)

    def test_incomplete_generation_is_dropped_previous_stays(self) -> None:
        packed = self.pack("e1")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        packet_bytes = (self.home / "waves/001/packets/e1.json").read_bytes()
        junk = self.wal / "deadbeef"
        junk.mkdir()
        (junk / "state.json").write_text("{}\n", encoding="utf-8")
        rec = run_of(self.tmp, "checkpoint", "--summary", "recover incomplete")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        self.assertFalse(junk.exists(), "incomplete generation must be discarded")
        self.assertEqual(
            (self.home / "waves/001/packets/e1.json").read_bytes(), packet_bytes
        )
        rec2 = run_of(self.tmp, "checkpoint", "--summary", "recover again")
        self.assertEqual(rec2.returncode, 0, rec2.stderr)
        self.assertEqual(
            (self.home / "waves/001/packets/e1.json").read_bytes(), packet_bytes
        )

    def test_crash_after_manifest_readers_stay_on_previous(self) -> None:
        first = self.pack("e1")
        self.assertEqual(first.returncode, 0, first.stderr)
        prev = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        prev_gen = prev["generation"]
        crashed = self.pack("e2", "s2", OF_WAL_CRASH="after-manifest")
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        current = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertEqual(current["generation"], prev_gen)
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("spawned     1 /", spawned_line(status.stdout))
        resume = run_of(self.tmp, "resume")
        self.assertEqual(resume.returncode, 0, resume.stderr)
        self.assertIn("e1", resume.stdout)
        self.assertNotIn("\n  e2\n", resume.stdout)
        rendered = run_of(
            self.tmp, "render", "--packet", ".orderfield/waves/001/packets/e2.json"
        )
        self.assertNotEqual(rendered.returncode, 0, rendered.stdout)
        rec = run_of(self.tmp, "checkpoint", "--summary", "replay wal")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        after = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertNotEqual(after["generation"], prev_gen)
        self.assertTrue((self.home / "waves/001/packets/e2.json").is_file())

    def test_crash_after_first_live_readers_see_current_before_mutator(self) -> None:
        first = self.pack("e1")
        self.assertEqual(first.returncode, 0, first.stderr)
        prev = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        prev_gen = prev["generation"]
        crashed = self.pack("e2", "s2", OF_WAL_CRASH="after-first-live")
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        current = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertNotEqual(current["generation"], prev_gen)
        self.assertTrue((self.wal / prev_gen).is_dir())
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("spawned     2 /", spawned_line(status.stdout))
        resume = run_of(self.tmp, "resume")
        self.assertEqual(resume.returncode, 0, resume.stderr)
        self.assertIn("e1", resume.stdout)
        self.assertIn("e2", resume.stdout)
        rendered = run_of(
            self.tmp, "render", "--packet", ".orderfield/waves/001/packets/e2.json"
        )
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        rec = run_of(self.tmp, "checkpoint", "--summary", "replay wal")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        rec2 = run_of(self.tmp, "checkpoint", "--summary", "replay wal again")
        self.assertEqual(rec2.returncode, 0, rec2.stderr)
        again = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertTrue((self.home / "waves/001/packets/e2.json").is_file())
        man = json.loads(
            (self.wal / again["generation"] / "MANIFEST.json").read_text(encoding="utf-8")
        )
        for rel, digest in man["files"].items():
            if rel == "session.json":
                continue
            live = self.home / rel
            self.assertTrue(live.is_file(), rel)
            self.assertEqual(sha256_file(live), digest, rel)

    def _init_with_brief(self) -> None:
        brief = self.tmp / "brief.md"
        brief.write_text("# Brief\n\n- exit code 0 on success\n", encoding="utf-8")
        r = run_of(
            self.tmp,
            "init",
            "--force",
            "--mission",
            "wal mission",
            "--phase",
            "explore",
            "--source-file",
            str(brief),
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_add_crash_before_pointer_keeps_previous_brief(self) -> None:
        self._init_with_brief()
        before_order = json.loads((self.home / "ORDER.json").read_text(encoding="utf-8"))
        before_spec = (self.home / "SPEC.md").read_text(encoding="utf-8")
        before_req = json.loads((self.home / "REQUIREMENTS.json").read_text(encoding="utf-8"))
        crashed = run_of(
            self.tmp,
            "spec",
            "--add",
            "ADD-001",
            "--text",
            "added under wal crash",
            env_extra={"OF_WAL_CRASH": "after-manifest"},
        )
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        live_order = json.loads((self.home / "ORDER.json").read_text(encoding="utf-8"))
        self.assertEqual(live_order["rev"], before_order["rev"])
        self.assertEqual((self.home / "SPEC.md").read_text(encoding="utf-8"), before_spec)
        live_req = json.loads((self.home / "REQUIREMENTS.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [r["id"] for r in live_req["requirements"]],
            [r["id"] for r in before_req["requirements"]],
        )
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertNotIn("HASH MISMATCH", status.stdout)
        rec = run_of(self.tmp, "checkpoint", "--summary", "replay spec add")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        after_req = json.loads((self.home / "REQUIREMENTS.json").read_text(encoding="utf-8"))
        self.assertIn("ADD-001", [r["id"] for r in after_req["requirements"]])
        after_spec = (self.home / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("ADD-001", after_spec)

    def test_spec_amend_crash_before_pointer_keeps_previous_brief(self) -> None:
        self._init_with_brief()
        before_spec = (self.home / "SPEC.md").read_text(encoding="utf-8")
        before_order = json.loads((self.home / "ORDER.json").read_text(encoding="utf-8"))
        crashed = run_of(
            self.tmp,
            "spec",
            "--amend",
            "WAL amend must not leak a mixed generation.",
            env_extra={"OF_WAL_CRASH": "after-manifest"},
        )
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        self.assertEqual((self.home / "SPEC.md").read_text(encoding="utf-8"), before_spec)
        live_order = json.loads((self.home / "ORDER.json").read_text(encoding="utf-8"))
        self.assertEqual(live_order["rev"], before_order["rev"])
        self.assertEqual(live_order["spec_hash"], before_order["spec_hash"])
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertNotIn("HASH MISMATCH", status.stdout)
        rec = run_of(self.tmp, "checkpoint", "--summary", "replay spec amend")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        after_spec = (self.home / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("WAL amend must not leak", after_spec)
        after_order = json.loads((self.home / "ORDER.json").read_text(encoding="utf-8"))
        self.assertNotEqual(after_order["spec_hash"], before_order["spec_hash"])

    def test_unpack_crash_before_pointer_restores_packet(self) -> None:
        packed = self.pack("e1")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        crashed = run_of(
            self.tmp,
            "unpack",
            "--child-id",
            "e1",
            env_extra={"OF_WAL_CRASH": "after-manifest"},
        )
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("spawned     1 /", spawned_line(status.stdout))
        resume = run_of(self.tmp, "resume")
        self.assertEqual(resume.returncode, 0, resume.stderr)
        self.assertIn("e1", resume.stdout)
        self.assertTrue(
            (self.home / "waves/001/packets/e1.json").is_file(),
            "uncommitted unpack must not hide the packet from CURRENT",
        )
        rec = run_of(self.tmp, "checkpoint", "--summary", "replay unpack")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        self.assertFalse((self.home / "waves/001/packets/e1.json").is_file())
        status2 = run_of(self.tmp, "status")
        self.assertEqual(status2.returncode, 0, status2.stderr)
        self.assertIn("spawned     0 /", spawned_line(status2.stdout))


if __name__ == "__main__":
    unittest.main()
