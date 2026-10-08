#!/usr/bin/env python3
"""W1 causal WAL: seq/parent chain, no mtime, fail closed (CS-1/2/3/6, INT-08, TV-1)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of.field as field  # noqa: E402
import of.wal as wal  # noqa: E402

OF_PY = SCRIPTS / "of.py"


def run_of(cwd: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault("OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"))
    for key in ("OF_WAL_CRASH", "OF_WAL_ADOPT_LIVE", "OF_CHILD", "OF_JSON", "OF_FIELD"):
        env.pop(key, None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(OF_PY), *args], cwd=str(cwd), capture_output=True, text=True, env=env
    )


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class WalChainCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-walchain-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ok(self.tmp, "init", "--mission", "m0", "--phase", "explore")

    def ok(self, cwd: Path, *args: str, **kw) -> subprocess.CompletedProcess[str]:
        r = run_of(cwd, *args, **kw)
        self.assertEqual(r.returncode, 0, f"of {' '.join(args)}: {r.stderr}")
        return r

    def home(self, root: Path | None = None) -> Path:
        return (root or self.tmp) / ".orderfield"

    def current(self, root: Path | None = None) -> dict:
        return load(self.home(root) / "wal" / "CURRENT.json")

    def snapshot(self, root: Path) -> tuple:
        order = load(self.home(root) / "ORDER.json")
        packets = sorted(p.name for p in (self.home(root) / "waves" / "001" / "packets").glob("*.json"))
        return order["rev"], order["mission"], list(order.get("constraints") or []), packets

    def build_history(self) -> None:
        self.ok(self.tmp, "patch", "--constraints-add", "c1")
        self.ok(self.tmp, "patch", "--constraints-add", "c2")
        self.ok(self.tmp, "pack", "--slice", "s1", "--role", "explorer", "--child-id", "e1")
        self.ok(self.tmp, "pack", "--slice", "s2", "--role", "explorer", "--child-id", "e2")

    def test_chain_fields_in_manifest_and_current(self) -> None:
        self.build_history()
        cur = self.current()
        gid = cur["generation"]
        man = load(self.home() / "wal" / gid / "MANIFEST.json")
        self.assertEqual(cur["seq"], man["seq"])
        self.assertTrue(gid.startswith(f"{man['seq']:08d}-"), gid)
        parent = load(self.home() / "wal" / man["parent"] / "MANIFEST.json")
        self.assertEqual(parent["seq"] + 1, man["seq"])
        parent_bytes = (self.home() / "wal" / man["parent"] / "MANIFEST.json").read_bytes()
        self.assertEqual(man["parent_manifest_sha256"], hashlib.sha256(parent_bytes).hexdigest())
        self.assertEqual(cur["order_sha256"], man["files"]["ORDER.json"])
        self.assertEqual(load(self.home() / "wal" / "MATERIALIZED.json")["generation"], gid)
        self.assertNotIn("st_mtime", (SCRIPTS / "of" / "wal.py").read_text(encoding="utf-8"))

    def _copy_and_skew(self, dest: Path, *, rounding: bool) -> None:
        shutil.copytree(self.tmp, dest, copy_function=shutil.copy)  # no metadata
        walh = self.home(dest) / "wal"
        cur_path = walh / "CURRENT.json"
        st = cur_path.stat()
        for man in walh.glob("*/MANIFEST.json"):
            if man.parent.name == load(cur_path)["generation"]:
                continue
            if rounding:
                os.utime(man, (int(st.st_atime), int(st.st_mtime)))
            else:
                os.utime(man, (st.st_atime + 100, st.st_mtime + 100))
        if rounding:
            for path in walh.rglob("*"):
                s = path.stat()
                os.utime(path, (int(s.st_atime), int(s.st_mtime)))

    def test_copy_with_older_manifests_newer_never_rolls_back(self) -> None:
        self.build_history()
        want = self.snapshot(self.tmp)
        head = self.current()
        for i in range(20):
            with self.subTest(trial=i):
                dest = self.tmp.parent / f"{self.tmp.name}-copy{i}"
                self.addCleanup(shutil.rmtree, dest, True)
                self._copy_and_skew(dest, rounding=(i % 2 == 1))
                self.ok(dest, "checkpoint", "--summary", f"after copy {i}")
                self.assertEqual(self.snapshot(dest), want)
                after = self.current(dest)
                self.assertEqual(after["seq"], head["seq"] + 1)
                man = load(self.home(dest) / "wal" / after["generation"] / "MANIFEST.json")
                self.assertEqual(man["parent"], head["generation"])

    def test_torn_current_generation_file_refuses_writers_and_keeps_evidence(self) -> None:
        self.build_history()
        gid = self.current()["generation"]
        (self.home() / "wal" / gid / "PHASE.md").write_bytes(b"")
        order_path = self.home() / "ORDER.json"
        data = load(order_path)
        data["mission"] = "HIJACKED by child"
        order_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        for _ in range(2):
            r = run_of(self.tmp, "checkpoint", "--summary", "after torn file")
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn("wal-broken", r.stderr)
        self.assertEqual(self.current()["generation"], gid)
        quarantined = list((self.home() / "wal" / "orphans").glob(f"corrupt-{gid}*"))
        self.assertEqual(len(quarantined), 1, "CURRENT generation must be kept as evidence")
        self.assertTrue((quarantined[0] / "MANIFEST.json").is_file())
        child = run_of(
            self.tmp, "checkpoint", "--summary", "child adopt",
            env_extra={"OF_WAL_ADOPT_LIVE": "1", "OF_CHILD": "e1"},
        )
        self.assertNotEqual(child.returncode, 0, "a child cannot adopt live")
        adopted = self.ok(
            self.tmp, "checkpoint", "--summary", "leader adopt",
            env_extra={"OF_WAL_ADOPT_LIVE": "1"},
        )
        self.assertIn("adopts live", adopted.stderr)
        self.ok(self.tmp, "checkpoint", "--summary", "healthy again")

    def test_rm_wal_with_rev_gt_1_refuses(self) -> None:
        self.build_history()
        before = (self.home() / "ORDER.json").read_bytes()
        self.assertGreater(load(self.home() / "ORDER.json")["rev"], 1)
        shutil.rmtree(self.home() / "wal")
        r = run_of(self.tmp, "patch", "--mission", "HIJACKED")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("wal-broken", r.stderr)
        self.assertEqual((self.home() / "ORDER.json").read_bytes(), before)
        self.ok(self.tmp, "checkpoint", "--summary", "adopt", env_extra={"OF_WAL_ADOPT_LIVE": "1"})
        self.assertEqual(self.current()["seq"], 1)

    def test_rm_current_json_refuses(self) -> None:
        self.build_history()
        (self.home() / "wal" / "CURRENT.json").unlink()
        r = run_of(self.tmp, "checkpoint", "--summary", "no current")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("wal-broken", r.stderr)

    def test_forged_generations_are_quarantined_not_published(self) -> None:
        self.build_history()
        cur = self.current()
        gid = cur["generation"]
        walh = self.home() / "wal"
        forged = {
            "bad-parent": {"parent": "deadbeefdead", "parent_manifest_sha256": cur["manifest_sha256"]},
            "bad-man-sha": {"parent": gid, "parent_manifest_sha256": "0" * 64},
            "far-seq": {"parent": gid, "parent_manifest_sha256": cur["manifest_sha256"], "seq": cur["seq"] + 5},
        }
        for name, chain in forged.items():
            dest = walh / f"{cur['seq'] + 1:08d}-{name}"
            shutil.copytree(walh / gid, dest)
            order = load(dest / "ORDER.json")
            order["mission"] = f"FORGED {name}"
            payload = (json.dumps(order, indent=2) + "\n").encode("utf-8")
            (dest / "ORDER.json").write_bytes(payload)
            man = load(dest / "MANIFEST.json")
            man.update({"generation": dest.name, "seq": cur["seq"] + 1, **chain})
            man["files"]["ORDER.json"] = hashlib.sha256(payload).hexdigest()
            (dest / "MANIFEST.json").write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
        r = self.ok(self.tmp, "checkpoint", "--summary", "after forge")
        self.assertIn("quarantined", r.stderr)
        self.assertEqual(load(self.home() / "ORDER.json")["mission"], "m0")
        orphans = sorted(p.name for p in (walh / "orphans").iterdir())
        self.assertEqual(len(orphans), 3, orphans)
        for p in walh.iterdir():
            self.assertNotIn("FORGED", (p / "ORDER.json").read_text() if (p / "ORDER.json").is_file() else "")

    def test_crash_after_current_then_resume_repairs_live(self) -> None:
        crashed = run_of(
            self.tmp, "patch", "--mission", "NEW mission", env_extra={"OF_WAL_CRASH": "after-current"}
        )
        self.assertNotEqual(crashed.returncode, 0)
        self.assertIn("wal-crash", crashed.stderr)
        self.assertEqual(load(self.home() / "ORDER.json")["mission"], "m0")
        self.ok(self.tmp, "resume")
        self.assertEqual(load(self.home() / "ORDER.json")["mission"], "NEW mission")
        self.assertEqual(
            load(self.home() / "wal" / "MATERIALIZED.json")["generation"], self.current()["generation"]
        )

    def test_planted_packet_is_quarantined_not_inherited(self) -> None:
        self.ok(self.tmp, "pack", "--slice", "s1", "--role", "explorer", "--child-id", "e1")
        pkt_dir = self.home() / "waves" / "001" / "packets"
        ghost = pkt_dir / "ghost.json"
        ghost.write_bytes((pkt_dir / "e1.json").read_bytes())
        r = self.ok(self.tmp, "checkpoint", "--summary", "after plant")
        self.assertIn("quarantined", r.stderr)
        self.assertFalse(ghost.exists())
        self.assertNotIn("waves/001/packets/ghost.json", self.current()["files"])
        gid_dirs = list((self.home() / "wal" / "orphans").glob("live-*/waves/001/packets/ghost.json"))
        self.assertEqual(len(gid_dirs), 1)

    def to_v0834_shape(self) -> dict:
        """Rewrite wal/ to the v0.8.34 shape: 12-hex ids, no seq/parent, no MATERIALIZED."""
        walh = self.home() / "wal"
        cur = self.current()
        rename: dict[str, str] = {}
        for gen in [p for p in walh.iterdir() if p.is_dir()]:
            new = gen.name.split("-", 1)[1]
            rename[gen.name] = new
            gen.rename(walh / new)
            man = load(walh / new / "MANIFEST.json")
            man = {k: man[k] for k in ("files", "deletions", "complete")}
            man.update({"v": 1, "generation": new})
            (walh / new / "MANIFEST.json").write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
        legacy = {"v": 1, "generation": rename[cur["generation"]], "published_at": cur["published_at"],
                  "files": cur["files"], "deletions": cur["deletions"]}
        (walh / "CURRENT.json").write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")
        (walh / "MATERIALIZED.json").unlink()
        return legacy

    def test_pre_chain_v0834_wal_is_adopted_without_rollback(self) -> None:
        self.ok(self.tmp, "patch", "--mission", "m1")
        self.ok(self.tmp, "patch", "--mission", "m2")
        walh = self.home() / "wal"
        legacy = self.to_v0834_shape()
        st = (walh / "CURRENT.json").stat()
        for gen in walh.iterdir():
            if gen.is_dir() and gen.name != legacy["generation"]:
                os.utime(gen / "MANIFEST.json", (st.st_atime + 100, st.st_mtime + 100))
        rev = load(self.home() / "ORDER.json")["rev"]
        self.ok(self.tmp, "checkpoint", "--summary", "first touch")
        order = load(self.home() / "ORDER.json")
        self.assertEqual((order["mission"], order["rev"]), ("m2", rev))
        after = self.current()
        self.assertEqual(after["seq"], rev + 1)
        man = load(walh / after["generation"] / "MANIFEST.json")
        self.assertEqual(man["parent"], legacy["generation"])

    def test_pre_chain_adopt_keeps_leader_live_spec_edit(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="of-walchain-spec-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.ok(root, "init", "--mission", "m", "--phase", "explore", "--source", "ORIGINAL BRIEF")
        self.ok(root, "patch", "--mission", "m2")
        self.to_v0834_shape_at(root)
        spec = self.home(root) / "SPEC.md"
        spec.write_text("REVISED BRIEF by leader\n", encoding="utf-8")
        r = self.ok(root, "spec", "--revise-file", ".orderfield/SPEC.md")
        self.assertNotIn("crash after commit", r.stderr)
        self.assertIn("REVISED BRIEF", spec.read_text(encoding="utf-8"))
        gen = self.home(root) / "wal" / self.current(root)["generation"]
        self.assertIn("REVISED BRIEF", (gen / "SPEC.md").read_text(encoding="utf-8"))

    def test_pre_chain_adopt_still_refuses_live_order_rewrite(self) -> None:
        self.ok(self.tmp, "patch", "--mission", "LEADER")
        self.to_v0834_shape()
        order_path = self.home() / "ORDER.json"
        data = load(order_path)
        data["mission"] = "HIJACKED"
        order_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        r = run_of(self.tmp, "checkpoint", "--summary", "after upgrade")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("silent rewrite", r.stderr)
        self.assertEqual(load(self.home() / "wal" / "MATERIALIZED.json")["generation"],
                         self.current()["generation"])

    def to_v0834_shape_at(self, root: Path) -> dict:
        saved, self.tmp = self.tmp, root
        try:
            return self.to_v0834_shape()
        finally:
            self.tmp = saved

    def hijack_live_order(self) -> None:
        self.ok(self.tmp, "patch", "--mission", "LEADER mission")
        order_path = self.home() / "ORDER.json"
        data = load(order_path)
        data["mission"] = "HIJACKED"
        order_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def assert_readers_refuse(self) -> None:
        for cmd in (("status",), ("resume",), ("render", "--packet", "x")):
            with self.subTest(cmd=cmd[0]):
                r = run_of(self.tmp, *cmd)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn("wal-broken", r.stderr)
                self.assertNotIn("HIJACKED", r.stdout)

    def test_zeroed_current_json_refuses_readers_never_live(self) -> None:
        self.hijack_live_order()
        (self.home() / "wal" / "CURRENT.json").write_bytes(b"\0" * 64)
        self.assert_readers_refuse()
        r = run_of(self.tmp, "checkpoint", "--summary", "x")
        self.assertIn("wal-broken", r.stderr)
        child = run_of(self.tmp, "status", env_extra={"OF_WAL_ADOPT_LIVE": "1", "OF_CHILD": "e1"})
        self.assertNotEqual(child.returncode, 0)
        leader = self.ok(self.tmp, "status", env_extra={"OF_WAL_ADOPT_LIVE": "1"})
        self.assertIn("untrusted", leader.stderr)

    def test_missing_current_generation_refuses_readers_never_live(self) -> None:
        self.hijack_live_order()
        shutil.rmtree(self.home() / "wal" / self.current()["generation"])
        self.assert_readers_refuse()

    def test_torn_current_generation_reads_its_bytes_not_live(self) -> None:
        self.hijack_live_order()
        gid = self.current()["generation"]
        (self.home() / "wal" / gid / "PHASE.md").write_bytes(b"")
        r = self.ok(self.tmp, "status")
        self.assertIn("does not hash", r.stderr)
        self.assertIn("LEADER mission", r.stdout)
        self.assertNotIn("HIJACKED", r.stdout)

    def test_revised_order_without_wal_warns_readers(self) -> None:
        self.hijack_live_order()
        shutil.rmtree(self.home() / "wal")
        r = self.ok(self.tmp, "status")
        self.assertIn("no WAL CURRENT", r.stderr)
        self.assertIn("untrusted", r.stderr)

    def test_migrate_adopts_a_field_from_before_the_wal(self) -> None:
        self.ok(self.tmp, "patch", "--mission", "m1")
        shutil.rmtree(self.home() / "wal")
        child = run_of(self.tmp, "migrate", env_extra={"OF_CHILD": "e1"})
        self.assertIn("wal-broken", child.stderr)
        r = self.ok(self.tmp, "migrate")
        self.assertIn("adopts live", r.stderr)
        self.assertEqual(self.current()["seq"], 1)
        self.ok(self.tmp, "checkpoint", "--summary", "after migrate")

    def test_corrupt_manifest_generation_is_quarantined_not_deleted(self) -> None:
        walh = self.home() / "wal"
        bad = walh / "00000009-badbadbadbad"
        shutil.copytree(walh / self.current()["generation"], bad)
        (bad / "MANIFEST.json").write_bytes(b"{torn")
        stage = walh / "00000009-stagestage00"
        stage.mkdir()
        (stage / "ORDER.json").write_text("{}", encoding="utf-8")
        r = self.ok(self.tmp, "checkpoint", "--summary", "after torn manifest")
        self.assertIn("corrupt MANIFEST", r.stderr)
        self.assertFalse(bad.exists())
        self.assertFalse(stage.exists(), "a stage without MANIFEST was never published")
        kept = list((walh / "orphans").glob("corrupt-00000009-badbadbadbad*"))
        self.assertEqual(len(kept), 1)
        self.assertEqual((kept[0] / "MANIFEST.json").read_bytes(), b"{torn")

    def test_promoted_legacy_field_keeps_its_wal(self) -> None:
        self.ok(self.tmp, "patch", "--mission", "m1")
        first_id = load(self.home() / "ORDER.json")["id"]
        self.ok(self.tmp, "new", "--mission", "sibling")
        self.ok(self.tmp, "--field", first_id, "patch", "--constraints-add", "after promote")
        promoted = self.home() / "fields" / first_id
        self.assertTrue((promoted / "wal" / "CURRENT.json").is_file())
        self.assertFalse((self.home() / "wal").exists())
        self.assertEqual(load(promoted / "ORDER.json")["mission"], "m1")

    def test_v0834_sibling_generation_left_in_root_wal_is_moved_home(self) -> None:
        self.ok(self.tmp, "new", "--mission", "sibling")
        sib_id = (self.home() / "ACTIVE").read_text(encoding="utf-8").strip()
        sib = self.home() / "fields" / sib_id
        gid = load(sib / "wal" / "CURRENT.json")["generation"]
        (self.home() / "wal").mkdir(exist_ok=True)
        (sib / "wal" / gid).rename(self.home() / "wal" / gid)  # v0.8.34 placement
        self.ok(self.tmp, "--field", sib_id, "checkpoint", "--summary", "sibling")
        self.assertEqual(load(sib / "ORDER.json")["mission"], "sibling")
        man = load(sib / "wal" / load(sib / "wal" / "CURRENT.json")["generation"] / "MANIFEST.json")
        self.assertEqual(man["parent"], gid)
        self.assertTrue((sib / "wal" / gid).is_dir())


class WalChainInProcess(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-walchain-ip-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "m0", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.home = self.tmp / ".orderfield"
        field.set_field_home(self.home)
        self.addCleanup(field.clear_field_home)

    def test_drift_lists_live_paths_that_differ_from_current(self) -> None:
        self.assertEqual(wal.FieldWal.drift(self.tmp), [])
        (self.home / "PHASE.md").write_text("tampered\n", encoding="utf-8")
        (self.home / "waves" / "001" / "packets").mkdir(parents=True, exist_ok=True)
        (self.home / "waves" / "001" / "packets" / "x.json").write_text("{}\n", encoding="utf-8")
        self.assertEqual(
            wal.FieldWal.drift(self.tmp), ["PHASE.md", "waves/001/packets/x.json"]
        )

    def test_commit_exits_clean_after_flip_when_materialize_fails(self) -> None:
        before = load(self.home / "wal" / "CURRENT.json")
        err = io.StringIO()
        with mock.patch.object(wal, "_materialize_generation", side_effect=OSError(28, "No space")):
            with contextlib.redirect_stderr(err):
                with wal.field_generation(self.tmp):
                    wal.dump_text(self.home / "PHASE.md", "phase two\n")
        self.assertIn("live materialize failed", err.getvalue())
        after = load(self.home / "wal" / "CURRENT.json")
        self.assertEqual(after["seq"], before["seq"] + 1)
        self.assertNotEqual((self.home / "PHASE.md").read_text(encoding="utf-8"), "phase two\n")
        with contextlib.redirect_stderr(io.StringIO()):
            wal.recover_field_wal(self.tmp)
        self.assertEqual((self.home / "PHASE.md").read_text(encoding="utf-8"), "phase two\n")

    def test_durable_fsync_accepts_a_file_descriptor(self) -> None:
        path = self.tmp / "probe"
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            os.write(fd, b"x")
            wal.durable_fsync(fd)
        finally:
            os.close(fd)
        self.assertIs(wal.FieldWal.durable_fsync, wal.durable_fsync)


if __name__ == "__main__":
    unittest.main()
