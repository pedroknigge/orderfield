#!/usr/bin/env python3
"""WAL-001 publish + WAL-002 CURRENT-only read; crash both sides at CLI/file."""
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

    def _reinit_e1(self) -> None:
        r = run_of(
            self.tmp, "init", "--force", "--mission", "wal mission", "--phase", "explore"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        packed = self.pack("e1")
        self.assertEqual(packed.returncode, 0, packed.stderr)

    def _committed_manifest(self) -> tuple[str, dict]:
        current = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        gid = str(current["generation"])
        man = json.loads(
            (self.wal / gid / "MANIFEST.json").read_text(encoding="utf-8")
        )
        return gid, man

    def _assert_generation_hashes_to_manifest(self) -> dict:
        gid, man = self._committed_manifest()
        files = man.get("files") or {}
        self.assertTrue(files, "committed generation has no files")
        for rel, digest in files.items():
            staged = self.wal / gid / rel
            self.assertTrue(staged.is_file(), rel)
            self.assertFalse(staged.is_symlink(), rel)
            self.assertEqual(sha256_file(staged), digest, rel)
        return man

    def _stable_committed_hashes(self, man: dict) -> dict[str, str]:
        files = {
            str(rel): str(digest)
            for rel, digest in (man.get("files") or {}).items()
        }
        files.pop("session.json", None)
        return files

    def _assert_committed_children(
        self,
        children: list[str],
        *,
        tombstoned: list[str] | None = None,
        stable_hashes: dict[str, str] | None = None,
    ) -> dict:
        """CURRENT generation files own counters/packets/prompts/tombstones.

        Does not treat live == new manifest as proof: that passes after a
        rollback. Hashes are checked on wal/<gid>/ against MANIFEST.
        """
        gid, man = self._committed_manifest()
        files = man.get("files") or {}
        deletions = [str(x) for x in (man.get("deletions") or [])]
        self._assert_generation_hashes_to_manifest()
        state = json.loads((self.wal / gid / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(
            state.get("children_spawned"),
            len(children),
            "committed children_spawned",
        )
        self.assertIn("session.json", files)
        session = json.loads(
            (self.wal / gid / "session.json").read_text(encoding="utf-8")
        )
        self.assertIsInstance(session, dict)
        self.assertEqual(sha256_file(self.wal / gid / "session.json"), files["session.json"])
        for child in children:
            pkt = f"waves/001/packets/{child}.json"
            prompt = f"waves/001/prompts/{child}.md"
            self.assertIn(pkt, files, pkt)
            self.assertIn(prompt, files, prompt)
            self.assertNotIn(pkt, deletions, pkt)
            self.assertTrue((self.wal / gid / pkt).is_file(), pkt)
            self.assertEqual(sha256_file(self.wal / gid / pkt), files[pkt], pkt)
            self.assertEqual(sha256_file(self.wal / gid / prompt), files[prompt], prompt)
        for child in tombstoned or []:
            pkt = f"waves/001/packets/{child}.json"
            prompt = f"waves/001/prompts/{child}.md"
            self.assertNotIn(pkt, files, pkt)
            self.assertNotIn(prompt, files, prompt)
            self.assertFalse((self.wal / gid / pkt).is_file(), pkt)
            self.assertFalse((self.home / pkt).is_file(), pkt)
        if stable_hashes is not None:
            got = self._stable_committed_hashes(man)
            self.assertEqual(got, stable_hashes)
        return man

    def _crash_pack_e2_after_current(self) -> dict:
        first = self.pack("e1")
        self.assertEqual(first.returncode, 0, first.stderr)
        prev = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        crashed = self.pack("e2", "s2", OF_WAL_CRASH="after-current")
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        current = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertNotEqual(current["generation"], prev["generation"])
        live_state = json.loads((self.home / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(
            live_state.get("children_spawned"),
            1,
            "after-current must not have rematerialized live state yet",
        )
        _gid, man = self._committed_manifest()
        self._assert_committed_children(["e1", "e2"])
        return man

    def _assert_readers_agree(
        self,
        children: list[str],
        *,
        packet: str | None,
        full: bool = True,
    ) -> None:
        """status/resume/render/… see one CURRENT generation; live may be mixed."""
        self._assert_generation_hashes_to_manifest()
        n = len(children)
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn(f"spawned     {n} /", spawned_line(status.stdout))
        self.assertNotIn("HASH MISMATCH", status.stdout)
        resume = run_of(self.tmp, "resume")
        self.assertEqual(resume.returncode, 0, resume.stderr)
        for child in children:
            self.assertIn(child, resume.stdout)
        if packet is None:
            missing = run_of(
                self.tmp, "render", "--packet", ".orderfield/waves/001/packets/e1.json"
            )
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
        else:
            pkt = f".orderfield/waves/001/packets/{packet}.json"
            rendered = run_of(self.tmp, "render", "--packet", pkt)
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            validated = run_of(self.tmp, "validate", pkt)
            self.assertEqual(validated.returncode, 0, validated.stderr)
        if not full:
            self._assert_generation_hashes_to_manifest()
            return
        pulse = run_of(self.tmp, "pulse")
        self.assertEqual(pulse.returncode, 0, pulse.stderr)
        contrast = run_of(self.tmp, "contrast")
        self.assertIn(contrast.returncode, (0, 2), contrast.stderr)
        spec_diff = run_of(self.tmp, "spec-diff")
        self.assertIn(spec_diff.returncode, (0, 2), spec_diff.stderr)
        order_v = run_of(self.tmp, "validate", ".orderfield/ORDER.json")
        self.assertEqual(order_v.returncode, 0, order_v.stderr)
        if packet is not None:
            pkt = f".orderfield/waves/001/packets/{packet}.json"
            handoff = run_of(self.tmp, "handoff", "--packet", pkt)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            spawned = run_of(
                self.tmp,
                "spawn",
                "--packet",
                pkt,
                "--adapter",
                "generic",
                "--dry-run",
            )
            self.assertEqual(spawned.returncode, 0, spawned.stderr)
        self._assert_generation_hashes_to_manifest()

    def test_crash_after_current_readers_see_committed_generation(self) -> None:
        first = self.pack("e1")
        self.assertEqual(first.returncode, 0, first.stderr)
        prev = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        prev_gen = prev["generation"]
        crashed = self.pack("e2", "s2", OF_WAL_CRASH="after-current")
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        current = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        self.assertNotEqual(current["generation"], prev_gen)
        self.assertTrue((self.wal / prev_gen).is_dir())
        live_state = json.loads((self.home / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(
            live_state.get("children_spawned"),
            1,
            "after-current must not have rematerialized live state yet",
        )
        self._assert_readers_agree(["e1", "e2"], packet="e2")
        rec = run_of(self.tmp, "checkpoint", "--summary", "replay after-current")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        rec2 = run_of(self.tmp, "checkpoint", "--summary", "replay after-current again")
        self.assertEqual(rec2.returncode, 0, rec2.stderr)
        self._assert_committed_children(["e1", "e2"])
        again = json.loads((self.wal / "CURRENT.json").read_text(encoding="utf-8"))
        man = json.loads(
            (self.wal / again["generation"] / "MANIFEST.json").read_text(encoding="utf-8")
        )
        for rel, digest in man["files"].items():
            if rel == "session.json":
                continue
            live = self.home / rel
            self.assertTrue(live.is_file(), rel)
            self.assertEqual(sha256_file(live), digest, rel)

    def test_crash_after_current_immediate_checkpoint_keeps_e2(self) -> None:
        """WAL-002 writer: checkpoint with no view first must not roll back e2."""
        man = self._crash_pack_e2_after_current()
        stable = self._stable_committed_hashes(man)
        rec = run_of(self.tmp, "checkpoint", "--summary", "writer recover immediate")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        self._assert_committed_children(["e1", "e2"], stable_hashes=stable)
        gid, _man = self._committed_manifest()
        session = json.loads(
            (self.wal / gid / "session.json").read_text(encoding="utf-8")
        )
        self.assertEqual(session.get("last_cmd"), "checkpoint")
        flying = session.get("in_flight") or []
        self.assertIn("e1", flying)
        self.assertIn("e2", flying)
        rec2 = run_of(self.tmp, "checkpoint", "--summary", "writer recover again")
        self.assertEqual(rec2.returncode, 0, rec2.stderr)
        self._assert_committed_children(["e1", "e2"], stable_hashes=stable)

    def test_crash_after_current_status_then_checkpoint_keeps_e2(self) -> None:
        """WAL-002 writer: status (reader, no overwrite) then checkpoint keeps e2."""
        man = self._crash_pack_e2_after_current()
        stable = self._stable_committed_hashes(man)
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("spawned     2 /", spawned_line(status.stdout))
        live_state = json.loads((self.home / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(
            live_state.get("children_spawned"),
            1,
            "reader materialize must not overwrite live counters",
        )
        rec = run_of(self.tmp, "checkpoint", "--summary", "writer recover after status")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        self._assert_committed_children(["e1", "e2"], stable_hashes=stable)
        gid, _man = self._committed_manifest()
        session = json.loads(
            (self.wal / gid / "session.json").read_text(encoding="utf-8")
        )
        flying = session.get("in_flight") or []
        self.assertIn("e1", flying)
        self.assertIn("e2", flying)

    def test_crash_after_current_unpack_immediate_checkpoint_keeps_tombstone(self) -> None:
        packed = self.pack("e1")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        crashed = run_of(
            self.tmp,
            "unpack",
            "--child-id",
            "e1",
            env_extra={"OF_WAL_CRASH": "after-current"},
        )
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        _gid, man = self._committed_manifest()
        self.assertIn("waves/001/packets/e1.json", man.get("deletions") or [])
        self.assertNotIn("waves/001/packets/e1.json", man.get("files") or {})
        stable = self._stable_committed_hashes(man)
        rec = run_of(self.tmp, "checkpoint", "--summary", "writer recover tombstone")
        self.assertEqual(rec.returncode, 0, rec.stderr)
        self._assert_committed_children([], tombstoned=["e1"], stable_hashes=stable)
        self._assert_readers_agree([], packet=None, full=False)

    def test_crash_after_every_live_file_readers_agree(self) -> None:
        first = self.pack("e1")
        self.assertEqual(first.returncode, 0, first.stderr)
        crashed = self.pack("e2", "s2", OF_WAL_CRASH="after-current")
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        _gid, man = self._committed_manifest()
        rels = list(man.get("files") or {})
        self.assertTrue(rels)
        for rel in rels:
            with self.subTest(crash=f"after-live:{rel}"):
                self._reinit_e1()
                crashed = self.pack("e2", "s2", OF_WAL_CRASH=f"after-live:{rel}")
                self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
                self.assertIn("wal-crash", crashed.stderr)
                self._assert_readers_agree(["e1", "e2"], packet="e2", full=False)

    def test_crash_after_current_unpack_hides_packet(self) -> None:
        packed = self.pack("e1")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        crashed = run_of(
            self.tmp,
            "unpack",
            "--child-id",
            "e1",
            env_extra={"OF_WAL_CRASH": "after-current"},
        )
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        self.assertIn("wal-crash", crashed.stderr)
        _gid, man = self._committed_manifest()
        self.assertIn("waves/001/packets/e1.json", man.get("deletions") or [])
        self._assert_readers_agree([], packet=None)

    def test_crash_after_every_tombstone_readers_agree(self) -> None:
        packed = self.pack("e1")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        crashed = run_of(
            self.tmp,
            "unpack",
            "--child-id",
            "e1",
            env_extra={"OF_WAL_CRASH": "after-current"},
        )
        self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
        _gid, man = self._committed_manifest()
        deletions = [str(x) for x in (man.get("deletions") or [])]
        self.assertTrue(deletions, "unpack generation must tombstone the packet")
        for rel in deletions:
            with self.subTest(crash=f"after-tombstone:{rel}"):
                self._reinit_e1()
                crashed = run_of(
                    self.tmp,
                    "unpack",
                    "--child-id",
                    "e1",
                    env_extra={"OF_WAL_CRASH": f"after-tombstone:{rel}"},
                )
                self.assertNotEqual(crashed.returncode, 0, crashed.stderr)
                self.assertIn("wal-crash", crashed.stderr)
                self._assert_readers_agree([], packet=None, full=False)

    def test_live_tamper_does_not_override_committed_bytes(self) -> None:
        packed = self.pack("e1")
        self.assertEqual(packed.returncode, 0, packed.stderr)
        order_path = self.home / "ORDER.json"
        data = json.loads(order_path.read_text(encoding="utf-8"))
        data["mission"] = "tampered live mission"
        order_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        status = run_of(self.tmp, "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("wal mission", status.stdout)
        self.assertNotIn("tampered live mission", status.stdout)
        self._assert_generation_hashes_to_manifest()


if __name__ == "__main__":
    unittest.main()
