"""Regression tests for v0.9.13 re-audit fixes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import of  # noqa: E402
from of.cli.issue_cmd import _refuse_child_issue_submit  # noqa: E402
from of.cli.wave import ChildForge  # noqa: E402
from of.field import field_lock, holds_field_lock  # noqa: E402
from of.pack import load_packet, packet_digest, validate_residual_for_packet  # noqa: E402
from of.regime import integration_input_digest, wave_report_covers_packets  # noqa: E402
from of.retain import _retention_link_targets  # noqa: E402
from of.wal import (  # noqa: E402
    LEGACY_CLOSE_KEY,
    LeaderKey,
    _authenticated_manifest,
    _load_wal_current,
    ensure_committed_field_view,
    legacy_close_adopted,
)

OF_CLI = Path(__file__).resolve().parents[1] / "scripts" / "of.py"


def run_of(cwd: Path, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    for key in ("OF_CHILD", "OF_HANDOFF_CHILD", "OF_FIELD", "OF_LEADER_KEY"):
        env.pop(key, None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(OF_CLI), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


class TestW7bMigrationCompatibility(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-v0913-mig-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "compat mission", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        p = run_of(
            self.tmp,
            "pack",
            "--child-id",
            "c1",
            "--role",
            "explorer",
            "--slice",
            "inspect",
        )
        self.assertEqual(p.returncode, 0, p.stderr)

    def _make_pre_w7b_field(self) -> tuple[str, str]:
        """Run a real integrate, then rewrite artifacts into authentic pre-0.9.12 shape."""
        import hashlib

        field_dir = self.tmp / ".orderfield"
        tmpl_path = field_dir / "waves" / "001" / "prompts" / "c1.RESIDUAL.template.json"
        tmpl = json.loads(tmpl_path.read_text(encoding="utf-8"))

        out_file = field_dir / "work" / "scratch" / "c1" / "out.md"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text("ok\n", encoding="utf-8")

        res_dir = field_dir / "waves" / "001" / "residuals"
        res_dir.mkdir(parents=True, exist_ok=True)
        res_path = res_dir / "c1.json"
        res = dict(tmpl)
        res["status"] = "done"
        res["result_ref"] = ".orderfield/work/scratch/c1/out.md"
        res["residual"] = dict(res.get("residual") or {})
        res["residual"]["evidence"] = (
            f"artifact_sha:{hashlib.sha256(out_file.read_bytes()).hexdigest()}"
        )
        res_path.write_text(json.dumps(res, indent=2), encoding="utf-8")

        integ = run_of(self.tmp, "integrate", "--apply")
        self.assertEqual(integ.returncode, 0, integ.stderr)

        # Now rewrite ORDER, state, packet, residual, template, report, and integrations/<hash>.json
        # to pre-0.9.12 (W7b) shape.
        order_path = field_dir / "ORDER.json"
        order = json.loads(order_path.read_text(encoding="utf-8"))
        order["thresholds"]["local_budget_pct"] = 80
        order["enabled_regimes"] = ["scale_up"]
        order_path.write_text(json.dumps(order, indent=2), encoding="utf-8")

        state_path = field_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["last_regime"] = "scale_up"
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        pkt_path = field_dir / "waves" / "001" / "packets" / "c1.json"
        pkt = json.loads(pkt_path.read_text(encoding="utf-8"))
        pkt["budget"]["tokens"] = 1000
        old_hash = packet_digest(pkt)
        pkt["packet_hash"] = old_hash
        pkt_path.write_text(json.dumps(pkt, indent=2), encoding="utf-8")

        tmpl["packet_hash"] = old_hash
        tmpl_path.write_text(json.dumps(tmpl, indent=2), encoding="utf-8")

        res["packet_hash"] = old_hash
        res_path.write_text(json.dumps(res, indent=2), encoding="utf-8")

        report_path = field_dir / "waves" / "001" / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        migrated_order = of.load_order(self.tmp)
        old_input_hash = integration_input_digest(
            self.tmp,
            1,
            [pkt],
            partial=bool(report["integration"].get("partial")),
            apply=bool(report["integration"].get("apply")),
            order=migrated_order,
            packet_hashes={"c1": old_hash},
            residuals_override={"c1": res},
        )
        old_rec = report["integration"]["record_path"]
        report["regime"] = "scale_up"
        report["caps_remaining"]["across_this_wave"] = 1
        report["integration"]["input_hash"] = old_input_hash
        report["integration"]["record_path"] = (
            f".orderfield/waves/001/integrations/{old_input_hash}.json"
        )
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        old_rec_path = self.tmp / old_rec
        if old_rec_path.is_file():
            old_rec_path.unlink()
        int_dir = field_dir / "waves" / "001" / "integrations"
        int_dir.mkdir(parents=True, exist_ok=True)
        (int_dir / f"{old_input_hash}.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        return old_hash, old_input_hash

    def test_pre_w7b_field_readable_before_and_after_migrate(self) -> None:
        old_hash, old_input_hash = self._make_pre_w7b_field()

        # Before migrate: read-side compatibility keeps state, order, residual, report valid.
        loaded_order = of.load_order(self.tmp)
        self.assertEqual(loaded_order["enabled_regimes"], ["hold"])
        loaded_state = of.load_state(self.tmp)
        self.assertEqual(loaded_state["last_regime"], "hold")

        pkt_path = self.tmp / ".orderfield" / "waves" / "001" / "packets" / "c1.json"
        loaded_pkt = load_packet(pkt_path)
        self.assertNotEqual(loaded_pkt["packet_hash"], old_hash)

        res_path = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "c1.json"
        res = json.loads(res_path.read_text(encoding="utf-8"))
        self.assertEqual(validate_residual_for_packet(res, loaded_pkt, self.tmp), [])

        report = of.load_wave_report(self.tmp / ".orderfield" / "waves" / "001" / "report.json")
        self.assertTrue(wave_report_covers_packets(self.tmp, loaded_state, report))

        # Run of migrate: packet, residual, template, report, and integrations/<hash>.json stay coherent.
        mig = run_of(self.tmp, "migrate")
        self.assertEqual(mig.returncode, 0, mig.stderr)

        new_pkt = json.loads(pkt_path.read_text(encoding="utf-8"))
        new_hash = new_pkt["packet_hash"]
        self.assertNotEqual(new_hash, old_hash)
        self.assertEqual(new_hash, packet_digest(new_pkt))

        new_res = json.loads(res_path.read_text(encoding="utf-8"))
        self.assertEqual(new_res["packet_hash"], new_hash)
        self.assertEqual(validate_residual_for_packet(new_res, new_pkt, self.tmp), [])

        tmpl_path = self.tmp / ".orderfield" / "waves" / "001" / "prompts" / "c1.RESIDUAL.template.json"
        if tmpl_path.is_file():
            tmpl = json.loads(tmpl_path.read_text(encoding="utf-8"))
            self.assertEqual(tmpl["packet_hash"], new_hash)

        new_state = json.loads((self.tmp / ".orderfield" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(new_state["last_regime"], "hold")

        new_report = json.loads(
            (self.tmp / ".orderfield" / "waves" / "001" / "report.json").read_text(encoding="utf-8")
        )
        new_input_hash = new_report["integration"]["input_hash"]
        self.assertNotEqual(new_input_hash, old_input_hash)
        self.assertEqual(new_report["regime"], "hold")
        self.assertTrue(
            (self.tmp / ".orderfield" / "waves" / "001" / "integrations" / f"{new_input_hash}.json").is_file()
        )
        self.assertTrue(wave_report_covers_packets(self.tmp, of.load_state(self.tmp), new_report))


class TestWalSecurityFixes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-v0913-wal-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "wal security", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_legacy_close_sha256_injection_in_current_is_refused(self) -> None:
        cur_path = self.tmp / ".orderfield" / "wal" / "CURRENT.json"
        cur = json.loads(cur_path.read_text(encoding="utf-8"))
        cur[LEGACY_CLOSE_KEY] = "a" * 64
        cur_path.write_text(json.dumps(cur, indent=2), encoding="utf-8")

        self.assertIsNone(_authenticated_manifest(self.tmp, cur))
        self.assertFalse(legacy_close_adopted(self.tmp, b"{}"))

    def test_legacy_close_sha256_is_bound_into_manifest_hmac(self) -> None:
        cur = _load_wal_current(self.tmp)
        self.assertIsNotNone(cur)
        assert cur is not None
        man_path = self.tmp / ".orderfield" / "wal" / cur["generation"] / "MANIFEST.json"
        man = json.loads(man_path.read_text(encoding="utf-8"))
        self.assertTrue(LeaderKey.verify_head(self.tmp, cur, man))

        # Mutating legacy_close_sha256 in MANIFEST invalidates the existing HMAC.
        tampered = dict(man)
        tampered[LEGACY_CLOSE_KEY] = "b" * 64
        self.assertFalse(LeaderKey.verify_head(self.tmp, cur, tampered))

    def test_v1_unsigned_downgrade_refused_when_leader_key_exists_on_disk(self) -> None:
        wal_dir = self.tmp / ".orderfield" / "wal"
        self.assertTrue((wal_dir / ".leader_key").is_file())
        cur_path = wal_dir / "CURRENT.json"
        cur = json.loads(cur_path.read_text(encoding="utf-8"))
        gen_id = "0123456789ab"
        gen_dir = wal_dir / gen_id
        gen_dir.mkdir(parents=True, exist_ok=True)
        # Copy live files into fake v1 generation.
        order_bytes = (self.tmp / ".orderfield" / "ORDER.json").read_bytes()
        (gen_dir / "ORDER.json").write_bytes(order_bytes)
        import hashlib

        order_sha = hashlib.sha256(order_bytes).hexdigest()
        v1_man = {
            "v": 1,
            "generation": gen_id,
            "complete": True,
            "files": {"ORDER.json": order_sha},
            "deletions": [],
        }
        (gen_dir / "MANIFEST.json").write_text(json.dumps(v1_man), encoding="utf-8")
        v1_cur = {
            "v": 1,
            "generation": gen_id,
            "files": {"ORDER.json": order_sha},
            "deletions": [],
        }
        cur_path.write_text(json.dumps(v1_cur), encoding="utf-8")

        # Without OF_LEADER_KEY env var, disk .leader_key must still reject v1 downgrade.
        self.assertIsNone(_authenticated_manifest(self.tmp, v1_cur))
        st = run_of(self.tmp, "status")
        self.assertNotEqual(st.returncode, 0)
        self.assertIn("WAL refused", st.stderr)


class TestLockAndRetentionAndChildForge(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-v0913-sec-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "sec checks", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ensure_committed_field_view_does_not_follow_lock_symlink(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="of-outside-"))
        self.addCleanup(shutil.rmtree, outside, True)
        target = outside / "pwned.txt"
        lock_path = self.tmp / ".orderfield" / "field.lock"
        if lock_path.exists() or lock_path.is_symlink():
            lock_path.unlink()
        lock_path.symlink_to(target)

        ensure_committed_field_view(self.tmp)
        self.assertFalse(target.exists())

    def test_holds_field_lock_is_thread_local(self) -> None:
        other_saw: list[bool] = []
        with field_lock(self.tmp, "worktree", generation=False):
            self.assertTrue(holds_field_lock(self.tmp))
            t = threading.Thread(target=lambda: other_saw.append(holds_field_lock(self.tmp)))
            t.start()
            t.join()
        self.assertEqual(other_saw, [False])
        self.assertFalse(holds_field_lock(self.tmp))

    def test_retention_link_targets_ignores_base_and_ancestor_and_oserror(self) -> None:
        base = self.tmp / ".orderfield"
        (base / "link_to_base").symlink_to(base)
        (base / "link_to_root").symlink_to(Path("/"))
        (base / "loop_a").symlink_to(base / "loop_b")
        (base / "loop_b").symlink_to(base / "loop_a")
        targets = _retention_link_targets(self.tmp)
        self.assertNotIn(base.resolve(), targets)
        self.assertNotIn(Path("/").resolve(), targets)

        # Also verify OSError during resolve() does not crash.
        with mock.patch.object(Path, "resolve", side_effect=[base.resolve(), OSError("EACCES")]):
            # Only ensure no unhandled OSError when resolving a symlink.
            pass
        orig_resolve = Path.resolve

        def flaky_resolve(p: Path, *a: object, **kw: object) -> Path:
            if p.name == "link_to_base":
                raise OSError("permission denied")
            return orig_resolve(p, *a, **kw)

        with mock.patch.object(Path, "resolve", flaky_resolve):
            targets2 = _retention_link_targets(self.tmp)
            self.assertNotIn(base.resolve(), targets2)

    def test_child_forge_forget_handoff_and_dispatch_order(self) -> None:
        # 1. of learn --forget refused for child
        res = run_of(self.tmp, "learn", "--forget", "lrn_00000001", env_extra={"OF_CHILD": "c1"})
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("refused while OF_CHILD=c1", res.stderr)

        # 2. ChildForge.refuse and _refuse_child_issue_submit honor OF_HANDOFF_CHILD
        with mock.patch.dict(os.environ, {"OF_HANDOFF_CHILD": "c1"}, clear=False):
            os.environ.pop("OF_CHILD", None)
            with self.assertRaises(SystemExit):
                ChildForge.refuse(self.tmp, "of pack")
            with self.assertRaises(SystemExit):
                _refuse_child_issue_submit()

        # 3. _dispatch refuses child BEFORE field_lock / materialize_current
        order_path = self.tmp / ".orderfield" / "ORDER.json"
        tampered_marker = order_path.read_text(encoding="utf-8") + "\n"
        order_path.write_text(tampered_marker, encoding="utf-8")
        res2 = run_of(self.tmp, "patch", "--mission", "hijack", env_extra={"OF_CHILD": "c1"})
        self.assertNotEqual(res2.returncode, 0)
        self.assertIn("refused while OF_CHILD=c1", res2.stderr)
        # Live file was not touched/rematerialized by field_lock because child was refused first.
        self.assertEqual(order_path.read_text(encoding="utf-8"), tampered_marker)

    def test_worktree_remove_force_refuses_live_order_tamper(self) -> None:
        # Init git repo so worktree add/remove works.
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.tmp, check=True)
        (self.tmp / "a.txt").write_text("v1\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.tmp, check=True)

        wt_dest = Path(tempfile.mkdtemp(prefix="of-wt-")) / "c1"
        self.addCleanup(shutil.rmtree, wt_dest.parent, True)
        add = run_of(self.tmp, "worktree", "add", "--child-id", "c1", "--path", str(wt_dest))
        self.assertEqual(add.returncode, 0, add.stderr)
        (wt_dest / "dirty.txt").write_text("unlanded\n", encoding="utf-8")

        # Tamper live ORDER.json before `worktree remove --force`.
        order_path = self.tmp / ".orderfield" / "ORDER.json"
        order = json.loads(order_path.read_text(encoding="utf-8"))
        order["mission"] = "TAMPERED LIVE MISSION"
        order_path.write_text(json.dumps(order, indent=2), encoding="utf-8")

        rem = run_of(self.tmp, "worktree", "remove", "--child-id", "c1", "--force")
        self.assertNotEqual(rem.returncode, 0)
        self.assertIn("ORDER.json", rem.stderr)


if __name__ == "__main__":
    unittest.main()
