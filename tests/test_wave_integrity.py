#!/usr/bin/env python3
"""W4 spawn/collect integrity: one writer per packet, child world = packet.

Pins per child (CS-5), partial collect commits (CS-7), forge guard on
pack/unpack/spawn (CC-2), handoff claims (handoff F4), residual template
(CC-1), ScopeWrite (HAKEN-04 / INT-04), sensor write globs, receipts
(INT-03), adapter pin precedence (F9), whitespace OwnedWrite. Children are
the generic fake adapter (OF_AGENT); every field lives in a temp dir.
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402
from of.receipt import EvidenceReceipt  # noqa: E402
from of_adapters import AdapterResume, SensorTrust, pick_adapter  # noqa: E402

OF_PY = SCRIPTS / "of.py"
WAVE = Path(".orderfield/waves/001")

# Fake child: writes a residual for its packet. MODE picks extra product
# writes. Identity comes from the packet; evidence hashes result_ref.
AGENT = r'''#!{python}
import hashlib, json, os, pathlib
root = pathlib.Path.cwd()
kid = os.environ["OF_CHILD"]
pkt = json.loads((root / ".orderfield/waves/001/packets" / (kid + ".json")).read_text())
mode = os.environ.get("FAKE_MODE", "")
if mode == "!crash":  # half-done work, then the leader's of spawn dies
    import signal
    notes = root / pkt["scratch_dir"] / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("half done\n")
    os.kill(os.getppid(), signal.SIGKILL)
    raise SystemExit(0)
for spec in filter(None, mode.split(",")):
    rel, _, text = spec.partition("=")
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text + "\n")
owns = pkt.get("owns_paths") or []
if owns:
    result = root / owns[0]
else:
    result = root / pkt["scratch_dir"] / "notes.md"
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text("mapped " + kid + "\n")
sha = hashlib.sha256(result.read_bytes()).hexdigest()
evidence = "mapped the slice at " + str(result.relative_to(root)) + "\nartifact_sha: " + sha
if owns:
    evidence += "\nrollback: git checkout -- " + owns[0]
res = {k: pkt[k] for k in ("packet_id", "packet_hash", "order_id", "order_rev", "wave", "child_id", "role")}
res.update({
    "status": "done",
    "result_ref": str(result.relative_to(root)),
    "residual": {"wants_to_change": [], "evidence": evidence, "proposed_patch": None},
    "metrics": {"uncertainty": 0.1, "divergence": 0.0, "tool_failures": 0, "novelty": False},
})
out = root / pkt["residual_path"]
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(res))
'''


class Field:
    """One temp field. ``git=True`` makes the product tree a git repo."""

    def __init__(self, test: unittest.TestCase, *, git: bool = False) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-w4-"))
        self.aux = Path(tempfile.mkdtemp(prefix="of-w4-aux-"))
        test.addCleanup(shutil.rmtree, self.tmp, True)
        test.addCleanup(shutil.rmtree, self.aux, True)
        self.test = test
        self.agent = self.aux / "agent.py"
        self.agent.write_text(AGENT.replace("{python}", sys.executable), encoding="utf-8")
        self.agent.chmod(0o755)
        self.env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
        for key in ("OF_AGENT", "OF_JSON", "OF_TRUST", "OF_ADAPTER", "OF_FIELD", "OF_CHILD"):
            self.env.pop(key, None)
        self.env["OF_LEARNINGS"] = str(self.aux / "learn.json")
        self.env["OF_SPAWN_REGISTRY"] = str(self.aux / "registry.json")
        self.env["OF_SPAWN_ENV"] = "FAKE_MODE"  # spawn_env is an allowlist
        if git:
            (self.tmp / "a.txt").write_text("alpha\n", encoding="utf-8")
            (self.tmp / "README.md").write_text("readme\n", encoding="utf-8")
            (self.tmp / "src").mkdir()
            (self.tmp / "src/app.py").write_text("print(1)\n", encoding="utf-8")
            self.git("init", "-q")
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "base")
        self.ok("init", "--mission", "m", "--phase", "build", "--agent-band", "10-50")

    def git(self, *args: str) -> None:
        subprocess.run(
            [
                "git",
                "-c", "user.email=w4@example.invalid",
                "-c", "user.name=w4",
                "-c", "commit.gpgsign=false",
                "-c", "core.hooksPath=/dev/null",
                *args,
            ],
            cwd=self.tmp,
            check=True,
            capture_output=True,
        )

    def of(self, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(OF_PY), *args],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env={**self.env, **extra},
            timeout=120,
        )

    def ok(self, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        r = self.of(*args, **extra)
        self.test.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def pack(self, child: str, role: str = "explorer", *owns: str) -> dict:
        flags = [x for p in owns for x in ("--owns-path", p)]
        self.ok("pack", "--slice", f"slice {child}", "--role", role, "--child-id", child, *flags)
        return self.packet(child)

    def packet(self, child: str) -> dict:
        return json.loads((self.tmp / WAVE / "packets" / f"{child}.json").read_text())

    def spawn(self, child: str, mode: str = "", **extra: str) -> subprocess.CompletedProcess[str]:
        return self.of(
            "spawn", "--adapter", "generic", "--packet", str(WAVE / "packets" / f"{child}.json"),
            OF_AGENT=str(self.agent), FAKE_MODE=mode, **extra,
        )

    def residual(self, child: str) -> Path:
        return self.tmp / WAVE / "residuals" / f"{child}.json"

    def write_done(self, child: str, data: dict | None = None) -> None:
        """Handoff child: the residual lands without a kernel-observed spawn."""
        pkt = self.packet(child)
        if data is None:
            notes = self.tmp / pkt["scratch_dir"] / "notes.md"
            notes.parent.mkdir(parents=True, exist_ok=True)
            notes.write_text(f"mapped {child}\n", encoding="utf-8")
            sha = hashlib.sha256(notes.read_bytes()).hexdigest()
            data = {k: pkt[k] for k in of.PACKET_IDENTITY_FIELDS}
            data.update(
                status="done",
                result_ref=f"{pkt['scratch_dir']}/notes.md",
                residual={
                    "wants_to_change": [],
                    "evidence": f"mapped the slice\nartifact_sha: {sha}",
                    "proposed_patch": None,
                },
                metrics={"uncertainty": 0.1, "divergence": 0.0, "tool_failures": 0, "novelty": False},
            )
        path = self.residual(child)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")


class ResidualPins(unittest.TestCase):
    def test_parallel_spawns_never_lose_a_pin(self) -> None:
        field = Field(self)
        kids = [f"c{i}" for i in range(4)]
        for kid in kids:
            field.pack(kid)
        pins = field.tmp / WAVE / "pins"
        with ThreadPoolExecutor(max_workers=4) as pool:
            for _round in range(10):
                shutil.rmtree(pins, ignore_errors=True)
                runs = list(pool.map(field.spawn, kids))
                for run in runs:
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertEqual(sorted(p.stem for p in pins.glob("*.json")), kids)
        self.assertFalse((field.tmp / WAVE / "residual_pins.json").exists())

    def test_spawn_record_without_pin_is_invalid(self) -> None:
        field = Field(self)
        field.pack("c1")
        field.ok("spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/c1.json"),
                 OF_AGENT=str(field.agent))
        (field.tmp / WAVE / "pins/c1.json").unlink()
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("rule=ResidualPin missing", r.stdout)

    def test_v0834_shared_pin_doc_still_honored(self) -> None:
        field = Field(self)
        field.pack("c1")
        field.write_done("c1")
        legacy = field.tmp / WAVE / "residual_pins.json"
        legacy.write_text(json.dumps({"c1": {"sha": "0" * 64, "by": "spawn"}}), encoding="utf-8")
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("rule=ResidualPin", r.stdout)
        digest = hashlib.sha256(field.residual("c1").read_bytes()).hexdigest()
        legacy.write_text(json.dumps({"c1": {"sha": digest, "by": "spawn"}}), encoding="utf-8")
        field.ok("collect")
        repinned = json.loads((field.tmp / WAVE / "pins/c1.json").read_text())
        self.assertEqual(repinned["by"], "collect")


class PartialCollect(unittest.TestCase):
    def test_partial_collect_commits_generation_then_exits_2(self) -> None:
        field = Field(self)
        field.pack("e1")
        field.pack("e2")
        field.residual("e1").parent.mkdir(parents=True, exist_ok=True)
        field.residual("e1").write_text('{"child_id": "e1", "status": "done"', encoding="utf-8")
        current = field.tmp / ".orderfield/wal/CURRENT.json"
        before = json.loads(current.read_text())["generation"]
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotEqual(json.loads(current.read_text())["generation"], before)
        session = json.loads((field.tmp / ".orderfield/session.json").read_text())
        self.assertEqual(session.get("last_cmd"), "collect")


class ChildForgeGuard(unittest.TestCase):
    def test_child_cannot_pack_unpack_or_spawn_in_its_field(self) -> None:
        field = Field(self)
        field.pack("c1")
        child = {"OF_CHILD": "c1"}
        attempts = [
            ("pack", "--slice", "grandchild", "--role", "explorer"),
            ("unpack", "--child-id", "c1"),
            ("spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/c1.json"), "--dry-run"),
            ("handoff", "--packet", str(WAVE / "packets/c1.json")),
        ]
        for argv in attempts:
            r = field.of(*argv, **child)
            self.assertNotEqual(r.returncode, 0, argv)
            self.assertIn("child-forge", r.stderr, argv)
        self.assertTrue((field.tmp / WAVE / "packets/c1.json").is_file())


class HandoffClaim(unittest.TestCase):
    def test_handoff_claim_refuses_second_writer(self) -> None:
        field = Field(self)
        field.pack("c1")
        field.ok("handoff", "--packet", str(WAVE / "packets/c1.json"))
        claim = json.loads((field.tmp / WAVE / "claims/c1.json").read_text())
        self.assertEqual(set(claim), {"mode", "harness", "session", "lease_expires"})
        self.assertEqual(claim["mode"], "handoff")
        r = field.spawn("c1")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("live handoff claim", r.stderr)
        self.assertFalse((field.tmp / WAVE / "spawns/c1.json").exists())
        forced = field.of(
            "spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/c1.json"),
            "--force-spawn", OF_AGENT=str(field.agent),
        )
        self.assertNotEqual(forced.returncode, 0, "--force-spawn needs --reason")

    def test_force_spawn_with_reason_overrides_a_live_claim(self) -> None:
        field = Field(self)
        field.pack("c1")
        field.ok("handoff", "--packet", str(WAVE / "packets/c1.json"))
        forced = field.of(
            "spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/c1.json"),
            "--force-spawn", "--reason", "handoff harness died", OF_AGENT=str(field.agent),
        )
        self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)
        self.assertIn("overridden: handoff harness died", forced.stderr)
        self.assertFalse((field.tmp / WAVE / "claims/c1.json").exists())
        record = json.loads((field.tmp / WAVE / "spawns/c1.json").read_text())
        self.assertEqual(record["force_reason"], "handoff harness died")
        field.ok("collect")

    def test_landed_residual_releases_the_claim(self) -> None:
        field = Field(self)
        field.pack("c1")
        field.ok("handoff", "--packet", str(WAVE / "packets/c1.json"))
        field.write_done("c1", {"child_id": "c1", "status": "done"})  # INVALID
        self.assertEqual(field.of("collect").returncode, 2)
        r = field.spawn("c1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        field.ok("collect")

    def test_crashed_spawn_recovers_with_force_spawn(self) -> None:
        field = Field(self)
        field.pack("c1")
        crashed = field.spawn("c1", "!crash")
        self.assertNotEqual(crashed.returncode, 0)
        record = json.loads((field.tmp / WAVE / "spawns/c1.json").read_text())
        self.assertNotIn("outcome", record)  # started-only, pid gone
        r = field.spawn("c1")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("nonempty scratch", r.stderr)
        forced = field.of(
            "spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/c1.json"),
            "--force-spawn", OF_AGENT=str(field.agent),
        )
        self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)
        field.ok("collect")

    def test_unwatched_scratch_refuses_spawn(self) -> None:
        field = Field(self)
        pkt = field.pack("c1")
        (field.tmp / pkt["scratch_dir"] / "PULSE").write_text("working\n", encoding="utf-8")
        r = field.spawn("c1")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nonempty scratch", r.stderr)


class ResidualTemplate(unittest.TestCase):
    def test_template_filled_per_child_md_collects(self) -> None:
        field = Field(self)
        pkt = field.pack("c1")
        template = field.tmp / WAVE / "prompts/c1.RESIDUAL.template.json"
        data = json.loads(template.read_text())
        for key in of.PACKET_IDENTITY_FIELDS:
            self.assertEqual(data[key], pkt[key])
        prompt = (field.tmp / WAVE / "prompts/c1.md").read_text()
        self.assertIn("c1.RESIDUAL.template.json", prompt)
        field.write_done("c1", data)  # unedited copy: status "" is not done
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        notes = field.tmp / pkt["scratch_dir"] / "notes.md"
        notes.write_text("mapped c1\n", encoding="utf-8")
        data["status"] = "done"
        data["result_ref"] = f"{pkt['scratch_dir']}/notes.md"
        data["residual"]["evidence"] = (
            "mapped LEASE-001\nartifact_sha: " + hashlib.sha256(notes.read_bytes()).hexdigest()
        )
        field.write_done("c1", data)
        field.ok("collect")


class ScopeWriteGate(unittest.TestCase):
    def test_explorer_product_write_is_invalid(self) -> None:
        field = Field(self, git=True)
        field.pack("e1")
        field.ok("spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/e1.json"),
                 OF_AGENT=str(field.agent), FAKE_MODE="a.txt=explorer edit")
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("rule=ScopeWrite", r.stdout)
        self.assertIn("a.txt", r.stdout)

    def test_implementer_outside_owns_paths_is_invalid(self) -> None:
        field = Field(self, git=True)
        field.pack("i1", "implementer", "src/app.py")
        field.ok("spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/i1.json"),
                 OF_AGENT=str(field.agent), FAKE_MODE="src/app.py=print(2),README.md=hijack")
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        line = next(x for x in r.stdout.splitlines() if "rule=ScopeWrite" in x)
        self.assertIn("README.md", line)
        self.assertNotIn("src/app.py,", line)

    def test_owned_writes_and_sibling_writes_collect(self) -> None:
        field = Field(self, git=True)
        field.pack("i1", "implementer", "src/app.py")
        field.pack("e1")
        field.ok("spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/i1.json"),
                 OF_AGENT=str(field.agent), FAKE_MODE="src/app.py=print(2)")
        field.write_done("e1")  # handoff explorer: diffed at collect, sees i1's path
        r = field.ok("collect")
        self.assertIn("ok=2", r.stdout)

    def test_series_write_into_idle_sibling_path_is_invalid(self) -> None:
        field = Field(self, git=True)
        field.pack("ia", "implementer", "src/app.py")
        field.ok("pack", "--slice", "slice ib", "--role", "implementer",
                 "--child-id", "ib", "--owns-path", "a.txt", "--force")
        field.ok("spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/ib.json"),
                 OF_AGENT=str(field.agent), FAKE_MODE="a.txt=b,src/app.py=print(9)")
        field.ok("spawn", "--adapter", "generic", "--packet", str(WAVE / "packets/ia.json"),
                 OF_AGENT=str(field.agent), FAKE_MODE="src/app.py=print(2)")
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        line = next(x for x in r.stdout.splitlines() if "rule=ScopeWrite" in x)
        self.assertIn("implementer ib", line)
        self.assertIn("src/app.py (owned by ia)", line)

    def test_non_git_tree_skips_with_note(self) -> None:
        field = Field(self)
        field.pack("e1")
        field.write_done("e1")
        (field.tmp / "stray.txt").write_text("x\n", encoding="utf-8")
        r = field.ok("collect")
        self.assertIn("ScopeWrite skipped (not a git work tree: e1)", r.stdout)


class OwnedWriteWhitespace(unittest.TestCase):
    def test_one_newline_is_not_an_owned_write(self) -> None:
        field = Field(self)
        src = field.tmp / "src/app.py"
        src.parent.mkdir()
        src.write_text("print(1)\n", encoding="utf-8")
        pkt = field.pack("i1", "implementer", "src/app.py")
        with src.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        data = {k: pkt[k] for k in of.PACKET_IDENTITY_FIELDS}
        data.update(
            status="done",
            result_ref="src/app.py",
            residual={
                "wants_to_change": [],
                "evidence": "artifact_sha: "
                + hashlib.sha256(src.read_bytes()).hexdigest()
                + "\nrollback: git checkout -- src/app.py",
                "proposed_patch": None,
            },
            metrics={"uncertainty": 0.1, "divergence": 0.0, "tool_failures": 0, "novelty": False},
        )
        field.write_done("i1", data)
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("owned_write_missing", r.stdout)


    def test_indentation_change_is_a_write(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-w4-ws-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        a, b, c = tmp / "a.py", tmp / "b.py", tmp / "c.py"
        a.write_text("if x:\n    y()\n", encoding="utf-8")
        b.write_text("if x:\n  y()\n", encoding="utf-8")
        c.write_text("if x:   \n\n    y()\n\n", encoding="utf-8")
        self.assertNotEqual(of.OwnedWrite.digest(a), of.OwnedWrite.digest(b))
        self.assertEqual(of.OwnedWrite.digest(a), of.OwnedWrite.digest(c))


class Receipts(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="of-w4-rcpt-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.scratch = self.root / ".orderfield/work/scratch/c1"

    def receipt(self, command_id: str, exit_code: int) -> str:
        data = ("tests/test_x.py::test_ok PASSED\n" * 200).encode()
        receipt, outcome = EvidenceReceipt.reduce(
            self.scratch, data, command_id=command_id, exit_code=exit_code,
            command="pytest -q", root=self.root,
        )
        self.assertEqual(outcome, EvidenceReceipt.ACCEPT)
        return f".orderfield/work/scratch/c1/logs/{command_id}.receipt.json"

    @staticmethod
    def done(*cites: str) -> dict:
        evidence = "ran the suite\n" + "\n".join(f"evidence_receipt: {c}" for c in cites)
        return {"status": "done", "residual": {"evidence": evidence}}

    def test_done_citing_failed_command_is_invalid(self) -> None:
        errs = EvidenceReceipt.errors(self.done(self.receipt("t1", 1)), self.root)
        self.assertTrue(any("exit=1" in e for e in errs), errs)
        self.assertEqual(EvidenceReceipt.errors(self.done(self.receipt("t0", 0)), self.root), [])

    def test_every_citation_is_verified(self) -> None:
        good = self.receipt("t0", 0)
        missing = ".orderfield/work/scratch/c1/logs/ghost.receipt.json"
        errs = EvidenceReceipt.errors(self.done(good, missing), self.root)
        self.assertTrue(errs)
        self.assertTrue(all("ghost" in e for e in errs), errs)


class AdapterPin(unittest.TestCase):
    def test_order_harness_outranks_of_adapter(self) -> None:
        with mock.patch.dict(os.environ, {"OF_ADAPTER": "codex"}):
            self.assertEqual(pick_adapter(None, "grok"), "grok")
            self.assertEqual(pick_adapter("claude", "grok"), "claude")
            self.assertEqual(pick_adapter(None, None), "codex")

    def test_resume_only_same_adapter_session(self) -> None:
        res = {"session_id": "s-1", "session_adapter": "cursor"}
        self.assertEqual(AdapterResume.argv_flags("claude", res), [])
        self.assertEqual(AdapterResume.argv_flags("cursor", res), ["--resume", "s-1"])
        self.assertEqual(
            AdapterResume.argv_flags("claude", {"session_id": "s-1"}, minted_by="cursor"), []
        )

    def test_sensor_writes_only_own_scratch_and_residual(self) -> None:
        pkt = {
            "role": "explorer",
            "scratch_dir": ".orderfield/work/scratch/c1",
            "residual_path": ".orderfield/waves/001/residuals/c1.json",
        }
        allowed = SensorTrust.flags("claude", "auto-edit", pkt)[-1]
        self.assertIn("Edit(./.orderfield/work/scratch/c1/**)", allowed)
        self.assertIn("Write(./.orderfield/waves/001/residuals/c1.json)", allowed)
        self.assertNotIn(".orderfield/**", allowed)
        nested = SensorTrust.write_globs(pkt, ".orderfield/fields/ord_0000abcd")
        self.assertEqual(nested[0], ".orderfield/fields/ord_0000abcd/work/scratch/c1/**")
        perm = json.loads(SensorTrust.env("opencode", "auto-edit", pkt)["OPENCODE_PERMISSION"])
        self.assertEqual(perm["edit"]["*"], "deny")
        self.assertNotIn(".orderfield/**", perm["edit"])


if __name__ == "__main__":
    unittest.main()
