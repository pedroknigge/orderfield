#!/usr/bin/env python3
"""WAL head binding and session.json writers (FUZZFIX).

CURRENT.manifest_sha256 names the head MANIFEST's bytes: a head MANIFEST
rewritten in place (still self-consistent) is wal-broken for writers and
readers. A v0.8.34 CURRENT without the field keeps working. `of learn`
writes session.json inside a locked generation, so no LIVE!=CURRENT follows.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import run_of  # noqa: E402


class WalHead(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="of-walhead-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.home = self.root / ".orderfield"
        self.ok("init", "--mission", "m", "--phase", "explore", "--source", "hold the head")
        self.ok("patch", "--constraints-add", "rule one")

    def ok(self, *args: str, env: dict | None = None):
        r = run_of(self.root, *args, env=env)
        self.assertEqual(r.returncode, 0, f"of {' '.join(args)}\n{r.stdout}\n{r.stderr}")
        return r

    def current(self) -> dict:
        return json.loads((self.home / "wal" / "CURRENT.json").read_text(encoding="utf-8"))

    def plan(self) -> dict:
        return json.loads(self.ok("resume", "--json").stdout)

    def test_rewritten_head_manifest_refuses_writers_and_readers(self) -> None:
        cur = self.current()
        man = self.home / "wal" / cur["generation"] / "MANIFEST.json"
        # Same files, same hashes, different bytes: intact, but not the
        # MANIFEST CURRENT published.
        man.write_text(json.dumps(json.loads(man.read_text(encoding="utf-8"))) + "\n", encoding="utf-8")
        for args in (("patch", "--constraints-add", "rule two"), ("resume",), ("status",)):
            r = run_of(self.root, *args)
            self.assertNotEqual(r.returncode, 0, f"of {' '.join(args)} accepted a foreign head MANIFEST")
            self.assertIn("wal-broken", r.stderr, args)

    def test_current_without_manifest_sha_still_works(self) -> None:
        cur = self.current()
        cur.pop("manifest_sha256")
        (self.home / "wal" / "CURRENT.json").write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")
        self.plan()
        self.ok("patch", "--constraints-add", "rule two")
        self.assertIn("rule two", json.loads((self.home / "ORDER.json").read_text())["constraints"])
        self.assertTrue(self.current().get("manifest_sha256"))

    def test_learn_leaves_live_equal_current(self) -> None:
        self.ok("learn", "field fact one")
        self.assertEqual(self.plan()["drift"], [])
        files = self.current()["files"]
        session = self.home / "wal" / self.current()["generation"] / "session.json"
        self.assertIn("session.json", files)
        self.assertEqual(json.loads(session.read_text())["last_cmd"], "learn")
        listed = self.ok("learn", "--list").stdout
        fid = next(w for w in listed.split() if w.startswith("lrn_"))
        self.ok("learn", "--forget", fid)
        self.assertEqual(self.plan()["drift"], [])

    def test_learn_does_not_publish_a_live_order_tamper(self) -> None:
        path = self.home / "ORDER.json"
        order = json.loads(path.read_text(encoding="utf-8"))
        order["mission"] = "child rewrote the mission"
        path.write_text(json.dumps(order, indent=2) + "\n", encoding="utf-8")
        run_of(self.root, "learn", "field fact two")
        staged = self.home / "wal" / self.current()["generation"] / "ORDER.json"
        self.assertEqual(json.loads(staged.read_text())["mission"], "m")
        self.assertEqual(self.plan()["action"], "restore")


if __name__ == "__main__":
    unittest.main()
