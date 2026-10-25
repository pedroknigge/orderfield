"""Regression tests for the run-1 security audit fixes (F01-F16).

Each test pins one invariant a fix established. They are unit-level and exercise
the kernel functions directly with dummy files; nothing runs a real harness, gh,
or the network.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import of.field as field  # noqa: E402
import of.wal as wal  # noqa: E402
import of_adapters  # noqa: E402
from of.pack import _unsafe_revert_rel  # noqa: E402


class TmpCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-sec-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / ".orderfield"
        self.home.mkdir()


class GitHardening(unittest.TestCase):
    def test_f01_run_git_neutralizes_fsmonitor_and_hooks(self) -> None:
        self.assertEqual(
            field.GIT_HARDEN,
            ("-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"),
        )
        self.assertEqual(field.GIT_HARDEN, of_adapters.GIT_HARDEN)


class NoFollowWrites(TmpCase):
    def test_f02_write_field_bytes_refuses_symlinked_leaf(self) -> None:
        outside = self.tmp / "outside.txt"
        outside.write_text("ORIGINAL\n", encoding="utf-8")
        (self.home / "FINAL.md").symlink_to(outside)
        with self.assertRaises(SystemExit):
            field.write_field_bytes(self.home, self.home / "FINAL.md", b"CHILD\n")
        self.assertEqual(outside.read_text(encoding="utf-8"), "ORIGINAL\n")

    def test_f02_write_field_bytes_refuses_symlinked_parent(self) -> None:
        victim = self.tmp / "victim"
        victim.mkdir()
        (self.home / "work").symlink_to(victim)
        with self.assertRaises(SystemExit):
            field.write_field_bytes(
                self.home, self.home / "work" / "scratch" / "x", b"CHILD\n"
            )
        self.assertFalse((victim / "scratch").exists())

    def test_f02_write_field_bytes_replaces_plain_file_atomically(self) -> None:
        leaf = field.write_field_bytes(self.home, self.home / "a" / "b.txt", b"ok\n")
        self.assertEqual(leaf.read_bytes(), b"ok\n")
        self.assertFalse(leaf.is_symlink())


class PhysicalAncestor(TmpCase):
    def test_f09_require_physical_under_refuses_symlinked_ancestor(self) -> None:
        victim = self.tmp / "victim"
        (victim / "scratch").mkdir(parents=True)
        (self.home / "work").symlink_to(victim)
        with self.assertRaises(SystemExit):
            field.require_physical_under(self.home, self.home / "work" / "scratch")

    def test_f09_require_physical_under_allows_real_tree(self) -> None:
        (self.home / "work" / "scratch").mkdir(parents=True)
        got = field.require_physical_under(self.home, self.home / "work" / "scratch")
        self.assertEqual(got, self.home / "work" / "scratch")


class GenerationIds(unittest.TestCase):
    def test_f04_valid_generation_id_accepts_minted_and_legacy(self) -> None:
        self.assertTrue(wal.valid_generation_id("00000002-adef9684fca7"))
        self.assertTrue(wal.valid_generation_id("627b95c5a89e"))
        self.assertTrue(wal.valid_generation_id("00000099-forged"))

    def test_f04_valid_generation_id_rejects_traversal(self) -> None:
        for bad in ("/scratch/a/.ssh", "../../../.ssh", "a/b", "..", "", ".x"):
            self.assertFalse(wal.valid_generation_id(bad), bad)


class ScopeRevert(unittest.TestCase):
    def test_f10_unsafe_revert_rel(self) -> None:
        for bad in ("/etc/passwd", "../x", ".orderfield/ORDER.json", "a\\b"):
            self.assertTrue(_unsafe_revert_rel(bad), bad)
        for ok in ("app.py", "src/mod.py", "vendor/sub/"):
            self.assertFalse(_unsafe_revert_rel(ok), ok)


class WalHmac(unittest.TestCase):
    """F11: the leader HMAC binds the generation file map, and a signing-era
    (chained) generation with a stripped signature is rejected."""

    KEY = "leader-secret-not-in-child-env"

    def _man(self, *, seq, files, signed):
        man = {
            "generation": "00000005-abcdefabcdef", "seq": seq, "parent": "p",
            "parent_manifest_sha256": "pm", "order_sha256": "o",
            "files": dict(files), "deletions": [],
        }
        if signed:
            key = self.KEY.encode("utf-8")
            man["hmac_sha256"] = hmac.new(
                key, wal.LeaderKey._manifest_chain_bytes(man), hashlib.sha256
            ).hexdigest()
        return man

    def test_f11_tampered_files_map_fails_verification(self) -> None:
        with mock.patch.dict(os.environ, {wal.LeaderKey.KEY_ENV: self.KEY}):
            man = self._man(seq=5, files={"ORDER.json": "aaa"}, signed=True)
            self.assertTrue(wal.LeaderKey.verify_head(None, man, man))
            # Child rewrites a committed packet into the files map; signature stale.
            forged = dict(man, files={"ORDER.json": "aaa", "waves/001/packets/c1.json": "bbb"})
            self.assertFalse(wal.LeaderKey.verify_head(None, forged, forged))

    def test_f11_chained_unsigned_head_is_rejected(self) -> None:
        # Legacy (no-seq) lenience is covered by tests.test_wal_chain's v0.8.34
        # adoption tests; here we pin that a chained head must be signed.
        with mock.patch.dict(os.environ, {wal.LeaderKey.KEY_ENV: self.KEY}):
            chained = self._man(seq=5, files={"ORDER.json": "aaa"}, signed=False)
            self.assertFalse(wal.LeaderKey.verify_head(None, chained, chained))
            self.assertFalse(wal.LeaderKey.verify_candidate(None, chained, chained))


class VerifyCmdEnv(unittest.TestCase):
    """F03: a packet verify_cmd runs as the leader but must not see the WAL
    signing key/token, even though the command string is leader-committed."""

    def test_f03_run_strips_leader_key_and_token(self) -> None:
        import of.receipt as receipt

        tmp = Path(tempfile.mkdtemp(prefix="of-sec-env-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        probe = (
            "import os,sys;"
            "sys.stdout.write('LEAK' if (os.environ.get('OF_LEADER_KEY') "
            "or os.environ.get('OF_LEADER_TOKEN')) else 'CLEAN')"
        )
        env = {"OF_LEADER_KEY": "secret-key", "OF_LEADER_TOKEN": "secret-token"}
        with mock.patch.dict(os.environ, env):
            code, out = receipt.KernelVerify._run(tmp, [sys.executable, "-c", probe], 30)
        self.assertEqual(code, 0, out)
        self.assertIn(b"CLEAN", out)
        self.assertNotIn(b"LEAK", out)


class SessionIdArgv(unittest.TestCase):
    def test_nv1_session_id_rejects_flag_like_values(self) -> None:
        for bad in ("--dangerously-skip-permissions", "--force", "-x", "--allowedTools=Bash"):
            self.assertEqual(
                of_adapters.AdapterResume.session_id({"session_id": bad}), "", bad
            )
            self.assertEqual(
                of_adapters.AdapterResume.argv_flags("claude", {"session_id": bad}), []
            )

    def test_nv1_session_id_accepts_opaque_token(self) -> None:
        sid = "abc123_DEF-45:67.ef"
        self.assertEqual(of_adapters.AdapterResume.session_id({"session_id": sid}), sid)
        flags = of_adapters.AdapterResume.argv_flags("claude", {"session_id": sid})
        self.assertEqual(flags, ["--resume", sid])
        self.assertFalse(any(f.startswith("-") and f != "--resume" for f in flags[1:]))


class SensorAllowlist(unittest.TestCase):
    def test_nv2_gh_api_is_not_sensor_allowlisted(self) -> None:
        self.assertNotIn("gh api", of_adapters.SensorTrust.COMMANDS)
        # read-only gh subcommands a sensor actually needs remain.
        self.assertIn("gh pr view", of_adapters.SensorTrust.COMMANDS)


class MigrateDrift(unittest.TestCase):
    """F08: of migrate must not sign live snapshot drift it is not itself migrating."""

    def setUp(self) -> None:
        from tests._harness import run_of

        self.run_of = run_of
        self.tmp = Path(tempfile.mkdtemp(prefix="of-migdrift-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.assertEqual(
            run_of(self.tmp, "init", "--mission", "m", "--phase", "explore").returncode, 0
        )
        r = run_of(
            self.tmp, "pack", "--slice", "s", "--role", "explorer",
            "--child-id", "c1", "--verify-cmd", "python3 -c pass",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.packet = self.tmp / ".orderfield/waves/001/packets/c1.json"

    def test_migrate_refuses_hash_consistent_live_packet_tamper(self) -> None:
        import of  # the kernel package

        doc = json.loads(self.packet.read_text(encoding="utf-8"))
        doc["verify_cmd"] = "touch /tmp/of-sec-should-not-run"
        if "packet_hash" in doc:
            doc["packet_hash"] = of.packet_digest(doc)  # keep it self-consistent
        self.packet.write_text(json.dumps(doc), encoding="utf-8")
        r = self.run_of(self.tmp, "migrate")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("LIVE!=CURRENT", r.stdout + r.stderr)

    def test_migrate_clean_field_is_allowed(self) -> None:
        r = self.run_of(self.tmp, "migrate")
        self.assertEqual(r.returncode, 0, r.stderr)


class AncestorCap(unittest.TestCase):
    def test_f16_cap_is_large_and_sentinel_is_not_a_child_id(self) -> None:
        self.assertGreaterEqual(field._MAX_SPAWN_ANCESTORS, 4096)
        # The fail-closed sentinel is truthy (so guards refuse) but not a valid id.
        from of.pack import CHILD_ID_RE

        self.assertTrue(field._ANCESTRY_UNBOUNDED)
        self.assertIsNone(CHILD_ID_RE.fullmatch(field._ANCESTRY_UNBOUNDED))


if __name__ == "__main__":
    unittest.main()
