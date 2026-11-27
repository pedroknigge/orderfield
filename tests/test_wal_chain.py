#!/usr/bin/env python3
"""W1 causal WAL: seq/parent chain, no mtime, fail closed (CS-1/2/3/6, INT-08, TV-1)."""
from __future__ import annotations

import contextlib
import hashlib
import hmac
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
    for key in (
        "OF_WAL_CRASH",
        "OF_WAL_ADOPT_LIVE",
        "OF_CHILD",
        "OF_JSON",
        "OF_FIELD",
        "OF_LEADER_KEY",
        "OF_LEADER_TOKEN",
    ):
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

    def _plant_single_generation(
        self,
        name: str,
        *,
        parent: str | None = None,
        strip_hmac: bool = False,
        corrupt_bytes: bool = False,
        legacy_close: str | None = None,
    ) -> str:
        """One seq+1 generation. The only fault is the flag that is set."""
        cur = self.current()
        gid = cur["generation"]
        walh = self.home() / "wal"
        dest = walh / f"{cur['seq'] + 1:08d}-{name}"
        shutil.copytree(walh / gid, dest)
        order = load(dest / "ORDER.json")
        order["mission"] = f"FORGED {name}"
        payload = (json.dumps(order, indent=2) + "\n").encode("utf-8")
        (dest / "ORDER.json").write_bytes(payload)
        man = load(dest / "MANIFEST.json")
        man["generation"] = dest.name
        man["seq"] = cur["seq"] + 1
        man["parent"] = gid if parent is None else parent
        man["parent_manifest_sha256"] = cur["manifest_sha256"]
        if not corrupt_bytes:
            digest = hashlib.sha256(payload).hexdigest()
            man["files"]["ORDER.json"] = digest
            man["order_sha256"] = digest
        man.pop("hmac_sha256", None)
        if legacy_close is not None:
            man[wal.LEGACY_CLOSE_KEY] = legacy_close
        if not strip_hmac:
            key = (walh / ".leader_key").read_text(encoding="utf-8").strip().encode("utf-8")
            man["hmac_sha256"] = hmac.new(
                key, wal.LeaderKey._manifest_chain_bytes(man), hashlib.sha256
            ).hexdigest()
        (dest / "MANIFEST.json").write_text(
            json.dumps(man, indent=2) + "\n", encoding="utf-8"
        )
        return dest.name

    def _assert_single_forge_quarantined(self, forged_name: str) -> None:
        r = self.ok(self.tmp, "checkpoint", "--summary", "after single forge")
        self.assertIn("quarantined", r.stderr)
        self.assertIn("not published", r.stderr)
        self.assertEqual(load(self.home() / "ORDER.json")["mission"], "m0")
        walh = self.home() / "wal"
        self.assertFalse((walh / forged_name).exists())
        orphans = list((walh / "orphans").glob(f"*{forged_name}*"))
        self.assertEqual(len(orphans), 1, [p.name for p in (walh / "orphans").iterdir()])
        self.assertNotEqual(self.current()["generation"], forged_name)

    def test_single_bad_parent_is_quarantined_not_published(self) -> None:
        forged = self._plant_single_generation("badparent", parent="deadbeefdead")
        self._assert_single_forge_quarantined(forged)

    def test_single_stripped_hmac_is_quarantined_not_published(self) -> None:
        forged = self._plant_single_generation("nohmac", strip_hmac=True)
        self._assert_single_forge_quarantined(forged)

    def test_single_nonintact_generation_is_quarantined_not_published(self) -> None:
        forged = self._plant_single_generation("tornfile", corrupt_bytes=True)
        self._assert_single_forge_quarantined(forged)

    def test_child_that_changes_legacy_close_sha256_is_quarantined(self) -> None:
        forged = self._plant_single_generation("legacy", legacy_close="b" * 64)
        self._assert_single_forge_quarantined(forged)

    def test_later_generation_carries_legacy_close_sha256(self) -> None:
        digest = "a" * 64
        current_path = self.home() / "wal" / "CURRENT.json"
        current = load(current_path)
        man_path = self.home() / "wal" / current["generation"] / "MANIFEST.json"
        man = load(man_path)
        man[wal.LEGACY_CLOSE_KEY] = digest
        man["hmac_sha256"] = wal.LeaderKey.sign_manifest(self.tmp, man)
        man_bytes = wal.json_payload_bytes(man)
        man_path.write_bytes(man_bytes)
        current[wal.LEGACY_CLOSE_KEY] = digest
        current["hmac_sha256"] = man["hmac_sha256"]
        current["manifest_sha256"] = hashlib.sha256(man_bytes).hexdigest()
        current_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        self.ok(self.tmp, "checkpoint", "--summary", "carry legacy close")
        after = self.current()
        self.assertEqual(after[wal.LEGACY_CLOSE_KEY], digest)
        after_man = load(self.home() / "wal" / after["generation"] / "MANIFEST.json")
        self.assertEqual(after_man[wal.LEGACY_CLOSE_KEY], digest)

    def test_checkpoint_refuses_symlinked_leader_key_and_keeps_canary(self) -> None:
        canary = self.tmp / "canary.txt"
        original = "user content stays\n"
        canary.write_text(original, encoding="utf-8")
        key = self.home() / "wal" / ".leader_key"
        self.assertTrue(key.is_file())
        self.assertFalse(key.is_symlink())
        key.unlink()
        key.symlink_to(canary)
        r = run_of(self.tmp, "checkpoint", "--summary", "probe")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("symlink", r.stderr)
        self.assertEqual(canary.read_text(encoding="utf-8"), original)
        self.assertNotIn("checkpoint saved", r.stdout)

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
        (walh / ".leader_key").unlink(missing_ok=True)
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
        before = {name: (self.home() / name).read_bytes() for name in ("ORDER.json", "state.json")}
        child = run_of(self.tmp, "migrate", env_extra={"OF_CHILD": "e1"})
        self.assertEqual(child.returncode, 1, child.stderr)
        self.assertIn("child-forge", child.stderr)
        self.assertFalse((self.home() / "wal").exists())
        self.assertEqual(before, {name: (self.home() / name).read_bytes() for name in before})
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


class SignedSnapshot(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.order = field.default_order("sample", "build")
        self.home = self.root / ".orderfield" / "fields" / self.order["id"]
        field.set_field_home(self.home)
        self.addCleanup(field.clear_field_home)
        with wal.field_generation(self.root):
            field.save_order(self.order, self.root)
            field.save_state(field.default_state(), self.root)
        self.pointer = wal.wal_current_path(self.root)
        self.current = load(self.pointer)
        self.key = wal.LeaderKey.path(self.root)

    def status(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(OF_PY), "--field", self.order["id"], "status"],
            cwd=self.root, capture_output=True, text=True,
            env={**os.environ, "OF_NO_UPDATE_CHECK": "1"},
        )

    def test_signed_genesis_requires_its_key_before_recovery(self) -> None:
        gid = self.current["generation"]
        self.pointer.unlink()
        (self.pointer.parent / "MATERIALIZED.json").unlink()
        backup = self.key.with_suffix(".backup")
        self.key.rename(backup)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            wal.recover_field_wal(self.root)
        self.assertFalse(self.pointer.exists())
        backup.rename(self.key)
        with mock.patch.dict(os.environ, {wal.LeaderKey.KEY_ENV: "different fixture key"}):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                wal.recover_field_wal(self.root)
        self.assertFalse(self.pointer.exists())
        self.assertEqual(wal.recover_field_wal(self.root), gid)
        self.assertEqual(load(self.pointer)["generation"], gid)

    def test_sibling_reads_check_manifest_and_its_key(self) -> None:
        expected = (self.home / "ORDER.json").read_bytes()
        self.assertEqual(wal.committed_bytes(self.root, "ORDER.json"), expected)
        backup = self.key.with_suffix(".backup")
        self.key.rename(backup)
        self.assertIsNone(wal.committed_bytes(self.root, "ORDER.json"))

        refused = self.status()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("wal-broken", refused.stderr)
        self.assertIn("leader key", refused.stderr)
        backup.rename(self.key)
        self.assertEqual(wal.committed_bytes(self.root, "ORDER.json"), expected)
        manifest = self.pointer.parent / self.current["generation"] / "MANIFEST.json"
        with manifest.open("ab") as handle:
            handle.write(b"\n")
        self.assertIsNone(wal.committed_bytes(self.root, "ORDER.json"))

    def test_nonregular_manifest_is_refused(self) -> None:
        manifest = self.pointer.parent / self.current["generation"] / "MANIFEST.json"
        manifest.unlink()
        manifest.mkdir()
        self.assertIsNone(wal.committed_bytes(self.root, "ORDER.json"))

    def test_pre_chain_field_remains_readable_after_adoption(self) -> None:
        gid = self.current["generation"]
        legacy_dir = self.pointer.parent / gid.split("-", 1)[1]
        (self.pointer.parent / gid).rename(legacy_dir)
        legacy = {"v": 1, "generation": legacy_dir.name, "files": self.current["files"], "deletions": []}
        (legacy_dir / "MANIFEST.json").write_text(json.dumps(legacy))
        self.pointer.write_text(json.dumps(dict(legacy, files={})))
        self.assertIsNone(wal.committed_bytes(self.root, "ORDER.json"))
        refused = self.status()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("wal-broken", refused.stderr)
        self.pointer.write_text(json.dumps(legacy))
        self.key.unlink()
        expected = (self.home / "ORDER.json").read_bytes()
        self.assertEqual(wal.committed_bytes(self.root, "ORDER.json"), expected)
        accepted = self.status()
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        wal.recover_field_wal(self.root)
        self.assertEqual(load(self.pointer)["adopted"], "pre-chain")
        self.assertEqual(wal.committed_bytes(self.root, "ORDER.json"), expected)
        (legacy_dir / "ORDER.json").write_bytes(b"damaged")
        self.assertIsNone(wal.committed_bytes(self.root, "ORDER.json"))


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

    def test_whitespace_only_order_is_not_a_silent_rewrite(self) -> None:
        live = self.home / "ORDER.json"
        obj = json.loads(live.read_text(encoding="utf-8"))
        live.write_text(json.dumps(obj, indent=4) + "\n", encoding="utf-8")
        wal._refuse_live_order_tamper(self.tmp)
        obj["mission"] = "HIJACKED"
        live.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            wal._refuse_live_order_tamper(self.tmp)

    def test_blocked_field_lock_does_not_rewrite_live(self) -> None:
        phase = self.home / "PHASE.md"
        phase.write_text("tampered\n", encoding="utf-8")
        with mock.patch.object(wal, "flock_acquire", side_effect=BlockingIOError) as acquire:
            wal.ensure_committed_field_view(self.tmp)
        self.assertTrue(acquire.called)
        self.assertEqual(phase.read_text(encoding="utf-8"), "tampered\n")

    def test_quarantine_leaves_a_directory_outside_wal(self) -> None:
        outside = self.tmp / "outside-wal"
        outside.mkdir()
        (outside / "keep.txt").write_text("stay\n", encoding="utf-8")
        dest = wal._quarantine(self.tmp, outside, "escape")
        self.assertIsNone(dest)
        self.assertEqual((outside / "keep.txt").read_text(encoding="utf-8"), "stay\n")

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
