#!/usr/bin/env python3
"""WAL-001 — stage + MANIFEST + publish; crash/recovery both sides at CLI/file."""
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


class FieldWalBothSides(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-wal-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "wal mission", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.home = self.tmp / ".orderfield"
        self.wal = self.home / "wal"

    def test_success_publish_writes_manifest_and_current(self) -> None:
        packed = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "e1"
        )
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
        packed = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "e1"
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        before = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        packet_bytes = (self.home / "waves/001/packets/e1.json").read_bytes()
        junk = self.wal / "deadbeef"
        junk.mkdir()
        (junk / "state.json").write_text("{}\n", encoding="utf-8")
        rec = run_of(self.tmp, "checkpoint", "--summary", "recover incomplete")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        self.assertFalse(junk.exists(), "incomplete generation must be discarded")
        after = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertEqual(after["generation"], before["generation"])
        self.assertEqual(
            (self.home / "waves/001/packets/e1.json").read_bytes(), packet_bytes
        )
        rec2 = run_of(self.tmp, "checkpoint", "--summary", "recover again")
        self.assertEqual(rec2.returncode, 0, rec2.stderr)
        again = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertEqual(again["generation"], before["generation"])

    def test_crash_after_first_live_recovers_idempotently(self) -> None:
        first = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer", "--child-id", "e1"
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        prev = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        prev_gen = prev["generation"]
        prev_dir = self.wal / prev_gen
        self.assertTrue(prev_dir.is_dir())
        crashed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "s2",
            "--role",
            "explorer",
            "--child-id",
            "e2",
            env_extra={"OF_WAL_CRASH": "after-first-live"},
        )
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        self.assertTrue(prev_dir.is_dir(), "previous published generation must remain readable")
        prev_packet = prev_dir / "waves/001/packets/e1.json"
        self.assertTrue(prev_packet.is_file())
        complete = [
            p
            for p in self.wal.iterdir()
            if p.is_dir() and (p / "MANIFEST.json").is_file() and p.name != prev_gen
        ]
        self.assertTrue(complete, "crashed pack must leave a complete unpublished MANIFEST")
        rec = run_of(self.tmp, "checkpoint", "--summary", "replay wal")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        current = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        gid = current["generation"]
        self.assertNotEqual(gid, prev_gen)
        man = json.loads((self.wal / gid / "MANIFEST.json").read_text(encoding="utf-8"))
        for rel, digest in man["files"].items():
            if rel == "session.json":
                continue  # checkpoint rewrites session after replay
            live = self.home / rel
            self.assertTrue(live.is_file(), rel)
            self.assertEqual(sha256_file(live), digest, rel)
        self.assertTrue(
            (self.home / "waves/001/packets/e2.json").is_file(),
            "recovery must finish the unpublished generation",
        )
        rec2 = run_of(self.tmp, "checkpoint", "--summary", "replay wal again")
        self.assertEqual(rec2.returncode, 0, rec2.stderr)
        again = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertEqual(again["generation"], gid)
        self.assertTrue(prev_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
