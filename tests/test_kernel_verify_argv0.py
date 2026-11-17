#!/usr/bin/env python3
"""#424: KernelVerify must not attest a child-writable argv0.

A scratch shim named ``python`` on PATH used to exit 0 and produce
``kernel_attested: true`` for ``python -m unittest`` on a repo with no
tests. The receipt named the command string and hashed no executable.
"""
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
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import of  # noqa: E402
from of.receipt import EvidenceReceipt, KernelVerify  # noqa: E402

OF_PY = SCRIPTS / "of.py"
CLEAN_ENV = (
    "OF_WAL_CRASH",
    "OF_WAL_ADOPT_LIVE",
    "OF_CHILD",
    "OF_HANDOFF_CHILD",
    "OF_LEADER_KEY",
    "OF_JSON",
    "OF_FIELD",
    "OF_ADAPTER",
    "OF_AGENT",
    "OF_SESSION_ID",
    "OF_TRUST",
    "OF_FIELD_STRICT",
)


def run_of(
    cwd: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    full.setdefault(
        "OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-argv0-learnings.json")
    )
    full["OF_SPAWN_REGISTRY"] = str(
        Path(tempfile.gettempdir()) / "of-argv0-spawn-registry.json"
    )
    for key in CLEAN_ENV:
        full.pop(key, None)
    if env:
        full.update(env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=full,
        timeout=60,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class KernelVerifyArgv0(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-argv0-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(
            [
                "git", "-C", str(self.tmp), "-c", "user.email=a@b", "-c",
                "user.name=t", "commit", "-q", "--allow-empty", "-m", "i",
            ],
            check=True,
        )
        self._saved_env = {
            key: os.environ.get(key) for key in ("PATH", "PYTHONPATH", "VIRTUAL_ENV")
        }

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def ok(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args, env=env)
        self.assertEqual(
            proc.returncode,
            0,
            f"of {' '.join(args)}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
        return proc

    def init_field(self) -> None:
        self.ok("init", "--mission", "t", "--source", "the helper returns five")

    def execute(
        self,
        command: str,
        *,
        scratch: Path | None = None,
        owns: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[dict, str, int]:
        if env:
            os.environ.update(env)
        kid = scratch or (self.tmp / ".orderfield" / "work" / "scratch" / "kid")
        kid.mkdir(parents=True, exist_ok=True)
        kwargs: dict = {}
        if owns is not None:
            kwargs["owns"] = owns
        return KernelVerify.execute(self.tmp, kid, command, **kwargs)

    def test_scratch_script_shim_is_not_attested(self) -> None:
        """The issue repro: a scratch ``python`` that exits 0 is not the verifier."""
        self.init_field()
        kid = self.tmp / ".orderfield" / "work" / "scratch" / "kid"
        kid.mkdir(parents=True)
        marker = self.tmp / "shim-ran"
        (kid / "python").write_text(
            f"#!/bin/sh\necho RAN > {marker}\necho OK\nexit 0\n",
            encoding="utf-8",
        )
        (kid / "python").chmod(0o755)
        os.environ["PATH"] = f"{kid}{os.pathsep}{os.environ.get('PATH', '')}"
        os.environ["PYTHONPATH"] = "src"
        receipt, _rel, code = self.execute("python -m unittest")
        self.assertNotEqual(code, 0)
        self.assertIsNot(receipt.get("kernel_attested"), True)
        self.assertIn("ChildWritableArgv0", str(receipt.get("rule") or ""))
        self.assertIn(str(kid / "python"), str(receipt.get("rule") or ""))
        self.assertFalse(marker.exists(), "the shim ran")
        self.assertIn("src", str((receipt.get("env_delta") or {}).get("PYTHONPATH") or ""))
        self.assertIn(str(kid), str((receipt.get("env_delta") or {}).get("PATH") or ""))

    def test_scratch_symlink_to_real_python_is_not_attested(self) -> None:
        """A scratch symlink whose target is the real interpreter is still child-writable."""
        self.init_field()
        kid = self.tmp / ".orderfield" / "work" / "scratch" / "kid"
        kid.mkdir(parents=True)
        (kid / "python").symlink_to(sys.executable)
        os.environ["PATH"] = f"{kid}{os.pathsep}{os.environ.get('PATH', '')}"
        receipt, rel, code = self.execute("python -c \"print(424)\"")
        self.assertNotEqual(code, 0)
        self.assertIsNot(receipt.get("kernel_attested"), True)
        self.assertIn("ChildWritableArgv0", str(receipt.get("rule") or ""))
        source = (self.tmp / receipt["source_path"]).read_text(encoding="utf-8")
        self.assertNotIn("424", source)
        self.assertTrue(rel)

    def test_project_venv_symlink_records_argv0(self) -> None:
        """``.venv/bin/python`` outside scratch and owns_paths still attests."""
        self.init_field()
        outside = Path(tempfile.mkdtemp(prefix="of-argv0-py-"))
        self.addCleanup(shutil.rmtree, outside, True)
        target = outside / "python"
        target.write_text("#!/bin/sh\necho OK\nexit 0\n", encoding="utf-8")
        target.chmod(0o755)
        venv_py = self.tmp / ".venv" / "bin" / "python"
        venv_py.parent.mkdir(parents=True)
        venv_py.symlink_to(target)
        receipt, _rel, code = self.execute(f"{venv_py} -c 'print(1)'")
        self.assertEqual(code, 0)
        self.assertIs(receipt.get("kernel_attested"), True)
        self.assertTrue(str(receipt.get("argv0") or "").endswith("/.venv/bin/python"))
        self.assertEqual(Path(receipt["argv0_realpath"]).resolve(), target.resolve())
        self.assertEqual(receipt["argv0_sha256"], _sha(target))
        source = (self.tmp / receipt["source_path"]).read_bytes()
        self.assertEqual(
            EvidenceReceipt.verify(receipt, source, root=self.tmp),
            EvidenceReceipt.ACCEPT,
        )

    def test_tampered_argv0_sha256_fails_signed_verification(self) -> None:
        self.init_field()
        outside = Path(tempfile.mkdtemp(prefix="of-argv0-py-"))
        self.addCleanup(shutil.rmtree, outside, True)
        target = outside / "python"
        target.write_text("#!/bin/sh\necho OK\nexit 0\n", encoding="utf-8")
        target.chmod(0o755)
        venv_py = self.tmp / ".venv" / "bin" / "python"
        venv_py.parent.mkdir(parents=True)
        venv_py.symlink_to(target)
        receipt, _rel, code = self.execute(str(venv_py))
        self.assertEqual(code, 0)
        self.assertIn("argv0_sha256", receipt)
        forged = json.loads(json.dumps(receipt))
        forged["argv0_sha256"] = "0" * 64
        self.assertIsNone(KernelVerify.signed_input_rows(self.tmp, forged))
        source = (self.tmp / receipt["source_path"]).read_bytes()
        self.assertEqual(
            EvidenceReceipt.verify(forged, source, root=self.tmp),
            f"{EvidenceReceipt.FALLBACK}:attestation",
        )

    def test_owns_paths_interpreter_is_not_attested(self) -> None:
        self.init_field()
        tool = self.tmp / "tools" / "python"
        tool.parent.mkdir()
        marker = self.tmp / "owned-ran"
        tool.write_text(
            f"#!/bin/sh\necho RAN > {marker}\nexit 0\n", encoding="utf-8"
        )
        tool.chmod(0o755)
        receipt, _rel, code = self.execute(str(tool), owns=["tools"])
        self.assertNotEqual(code, 0)
        self.assertIsNot(receipt.get("kernel_attested"), True)
        self.assertIn("owns_paths", str(receipt.get("rule") or ""))
        self.assertFalse(marker.exists())

    def test_child_worktree_interpreter_is_not_attested(self) -> None:
        self.init_field()
        wt = self.tmp.parent / f"{self.tmp.name}-wt"
        self.addCleanup(shutil.rmtree, wt, True)
        added = subprocess.run(
            ["git", "-C", str(self.tmp), "worktree", "add", "--detach", str(wt)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        self.addCleanup(
            subprocess.run,
            ["git", "-C", str(self.tmp), "worktree", "remove", "--force", str(wt)],
            check=False,
        )
        from of.field import save_worktrees

        save_worktrees(self.tmp, {"trees": {"kid": {"path": str(wt)}}})
        marker = self.tmp / "wt-ran"
        shim = wt / "python"
        shim.write_text(f"#!/bin/sh\necho RAN > {marker}\nexit 0\n", encoding="utf-8")
        shim.chmod(0o755)
        os.environ["PATH"] = f"{wt}{os.pathsep}{os.environ.get('PATH', '')}"
        receipt, _rel, code = self.execute("python -c 'print(1)'")
        self.assertNotEqual(code, 0)
        self.assertIsNot(receipt.get("kernel_attested"), True)
        self.assertIn("worktree", str(receipt.get("rule") or ""))
        self.assertFalse(marker.exists())

    def _pack_and_residual(self, verify_cmd: str) -> None:
        self.ok(
            "spec", "--add", "REQ-001", "--surface", "contract",
            "--text", "the helper returns five",
        )
        self.ok(
            "pack",
            "--slice", "implement helper.py",
            "--role", "implementer",
            "--child-id", "kid",
            "--owns-path", "helper.py",
            "--owns-requirement", "REQ-001",
            "--verify-cmd", verify_cmd,
            "--verify-req", "REQ-001",
        )
        from of.pack import OwnedWrite

        pkt_path = self.tmp / ".orderfield/waves/001/packets/kid.json"
        OwnedWrite.ensure(self.tmp, json.loads(pkt_path.read_text(encoding="utf-8")))
        pkt = json.loads(pkt_path.read_text(encoding="utf-8"))
        res = json.loads(
            (ROOT / "assets" / "fixtures" / "residual.done.json").read_text(encoding="utf-8")
        )
        for key in of.PACKET_IDENTITY_FIELDS:
            res[key] = pkt[key]
        res["role"] = pkt["role"]
        res["status"] = "done"
        note = self.tmp / ".orderfield/work/scratch/kid/result.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("done result\n", encoding="utf-8")
        res["result_ref"] = note.relative_to(self.tmp).as_posix()
        rem = res.setdefault("residual", {})
        rem["wants_to_change"] = []
        rem["proposed_patch"] = None
        rem["evidence"] = "implemented owned slice"
        if of.CloseEvidence.stamp_proof(res, pkt, self.tmp) is None:
            rem["evidence"] = of.CloseEvidence.attach(
                "implemented owned slice", note, rollback="git checkout -- ."
            )
        dest = self.tmp / pkt["residual_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")

    def test_collect_shim_does_not_stamp_verified_contract(self) -> None:
        self.init_field()
        self._pack_and_residual("python -c \"print('ok')\"")
        kid = self.tmp / ".orderfield/work/scratch/kid"
        marker = self.tmp / "collect-shim-ran"
        (kid / "python").write_text(
            f"#!/bin/sh\necho RAN > {marker}\nexit 0\n", encoding="utf-8"
        )
        (kid / "python").chmod(0o755)
        proc = run_of(
            self.tmp,
            "collect",
            env={"PATH": f"{kid}{os.pathsep}{os.environ.get('PATH', '')}"},
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("INVALID", proc.stdout)
        self.assertIn("ChildWritableArgv0", proc.stdout)
        self.assertNotIn("verified_by_kernel", proc.stdout)
        self.assertFalse(marker.exists())
        reqs = json.loads(
            (self.tmp / ".orderfield/REQUIREMENTS.json").read_text(encoding="utf-8")
        )
        self.assertNotEqual(reqs["requirements"][0]["status"], "verified_contract")

    def test_collect_exit_127_names_a_host_program(self) -> None:
        self.init_field()
        self._pack_and_residual("of-no-such-bin-424 -m unittest")
        proc = run_of(self.tmp, "collect")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("exit=127", proc.stdout)
        self.assertIn("python3 -m unittest", proc.stdout)
        self.assertIn("Do not put a child's scratch", proc.stdout)
        self.assertNotIn("verified_by_kernel", proc.stdout)

    def test_closed_receipt_keeps_argv0_and_env_delta(self) -> None:
        self.init_field()
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "thing.py").write_text("VALUE = 5\n", encoding="utf-8")
        self.ok(
            "spec", "--add", "HEL-001", "--surface", "contract",
            "--text", "the helper returns five",
        )
        self.ok(
            "spec", "--verified-contract", "HEL-001", "--run",
            f"{sys.executable} -c \"import thing; print('helper five')\"",
            env={"PYTHONPATH": "src", "VIRTUAL_ENV": str(self.tmp / ".venv")},
        )
        receipt_path = (
            self.tmp / ".orderfield/work/scratch/_leader_verify/logs/spec-hel-001.receipt.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertIs(receipt.get("kernel_attested"), True)
        self.assertTrue(receipt.get("argv0"))
        self.assertEqual(receipt.get("argv0_sha256"), _sha(Path(receipt["argv0_realpath"])))
        self.assertEqual(receipt["env_delta"]["PYTHONPATH"], "src")
        self.assertEqual(receipt["env_delta"]["VIRTUAL_ENV"], str(self.tmp / ".venv"))
        closed = self.ok("close")
        self.assertIn("CLOSED", closed.stdout)
        self.assertFalse(receipt_path.exists(), "scratch was not wiped")
        close_doc = json.loads(
            (self.tmp / ".orderfield/CLOSE.json").read_text(encoding="utf-8")
        )
        row = next(r for r in close_doc["receipts"] if r["path"].endswith("spec-hel-001.receipt.json"))
        archived = json.loads(
            (self.tmp / ".orderfield" / row["evidence"]).read_text(encoding="utf-8")
        )
        self.assertEqual(archived.get("argv0"), receipt["argv0"])
        self.assertEqual(archived.get("argv0_sha256"), receipt["argv0_sha256"])
        self.assertEqual(archived.get("env_delta"), receipt["env_delta"])


if __name__ == "__main__":
    unittest.main()
