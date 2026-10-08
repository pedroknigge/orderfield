#!/usr/bin/env python3
"""W3: deterministic, packet-targeted `next` and read-side truth.

D4 orphan, D5 truncated residual, D6 duplicate writer / TZ liveness, D8
read-path tamper, D9 ACTIVE, D13 next is a function of disk, INT-06 forged
close. Each case drives the shipped CLI in a scratch tree.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of.field as field  # noqa: E402

OF_PY = SCRIPTS / "of.py"
CLEAN_ENV = ("OF_WAL_CRASH", "OF_WAL_ADOPT_LIVE", "OF_CHILD", "OF_JSON", "OF_FIELD",
             "OF_ADAPTER", "OF_AGENT", "OF_SESSION_ID", "OF_TRUST", "OF_FIELD_STRICT")

# Writes a packet-bound explorer `done` residual (the child's whole job).
MKRES = r'''
import json, sys
from pathlib import Path
root, cid = Path(sys.argv[1]), sys.argv[2]
home = root / ".orderfield"
pkt = json.loads((home / "waves/001/packets" / (cid + ".json")).read_text())
note = home / "work/scratch" / cid / "notes.md"
note.parent.mkdir(parents=True, exist_ok=True)
note.write_text("finding: a.py:1 defines main\n")
keys = ("packet_id", "packet_hash", "order_id", "order_rev", "wave", "child_id", "role")
res = {k: pkt[k] for k in keys}
res.update({
    "status": "done",
    "result_ref": note.relative_to(root).as_posix(),
    "residual": {"wants_to_change": [], "proposed_patch": None,
                 "evidence": "a.py:1 defines main (read with sed -n 1p a.py)"},
    "metrics": {"uncertainty": 0.1, "divergence": 0.0, "tool_failures": 0, "novelty": False},
})
dest = root / pkt["residual_path"]
dest.parent.mkdir(parents=True, exist_ok=True)
tmp = dest.with_suffix(".tmp")
tmp.write_text(json.dumps(res, indent=2) + "\n")
tmp.replace(dest)
'''


def run_of(cwd: Path, *args: str, env: dict | None = None, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    full = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    full.setdefault("OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"))
    full["OF_SPAWN_REGISTRY"] = str(Path(tempfile.gettempdir()) / "of-w3-spawn-registry.json")
    for key in CLEAN_ENV:
        full.pop(key, None)
    full.update(env or {})
    return subprocess.run(
        [sys.executable, str(OF_PY), *args], cwd=str(cwd), capture_output=True,
        text=True, env=full, timeout=timeout,
    )


def tree_bytes(root: Path) -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class ResumeNext(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-w3-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        self.mkres = self.tmp.parent / f"{self.tmp.name}-mkres.py"
        self.mkres.write_text(MKRES, encoding="utf-8")
        self.addCleanup(self.mkres.unlink)
        self.ok("init", "--mission", "w3 next", "--phase", "explore")

    # -- helpers ---------------------------------------------------------
    def ok(self, *args: str, cwd: Path | None = None, **kw) -> subprocess.CompletedProcess[str]:
        r = run_of(cwd or self.tmp, *args, **kw)
        self.assertEqual(r.returncode, 0, f"of {' '.join(args)}\n{r.stdout}\n{r.stderr}")
        return r

    def pack(self, cid: str) -> str:
        self.ok("pack", "--slice", f"read the tree for {cid}", "--role", "explorer", "--child-id", cid)
        return f".orderfield/waves/001/packets/{cid}.json"

    def residual(self, cid: str, root: Path | None = None) -> Path:
        subprocess.run([sys.executable, str(self.mkres), str(root or self.tmp), cid], check=True)
        return (root or self.tmp) / ".orderfield" / "waves" / "001" / "residuals" / f"{cid}.json"

    def plan(self, cwd: Path | None = None, **kw) -> dict:
        r = self.ok("resume", "--json", cwd=cwd, **kw)
        return json.loads(r.stdout)

    def spawn_record(self, cid: str, meta: dict) -> Path:
        path = self.tmp / ".orderfield" / "waves" / "001" / "spawns" / f"{cid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"child_id": cid, "wave": 1, "started_at": field.utc_now(), **meta}),
                        encoding="utf-8")
        return path

    @staticmethod
    def dead_pid() -> int:
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        return proc.pid

    # -- D4: orphan -------------------------------------------------------
    def test_killed_leader_mid_spawn_settles_by_disk(self) -> None:
        packet = self.pack("ex1")
        bindir = self.tmp.parent / f"{self.tmp.name}-bin"
        bindir.mkdir()
        self.addCleanup(shutil.rmtree, bindir, True)
        fake = bindir / "claude"
        fake.write_text(f"#!/bin/sh\nsleep 1\n{sys.executable} {self.mkres} {self.tmp} ex1\n", encoding="utf-8")
        fake.chmod(0o755)
        env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "PATH": f"{bindir}:{os.environ['PATH']}",
               "OF_SPAWN_REGISTRY": str(Path(tempfile.gettempdir()) / "of-w3-spawn-registry.json")}
        for key in CLEAN_ENV:
            env.pop(key, None)
        leader = subprocess.Popen(
            [sys.executable, str(OF_PY), "spawn", "--adapter", "claude", "--packet", packet],
            cwd=str(self.tmp), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        record = self.tmp / ".orderfield" / "waves" / "001" / "spawns" / "ex1.json"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if record.is_file() and "pid" in json.loads(record.read_text() or "{}"):
                break
            time.sleep(0.05)
        leader.send_signal(signal.SIGKILL)  # harness tool timeout: finalize never runs
        leader.wait()
        residual = self.tmp / ".orderfield" / "waves" / "001" / "residuals" / "ex1.json"
        while time.monotonic() < deadline and not residual.is_file():
            time.sleep(0.05)
        meta = json.loads(record.read_text())
        self.assertNotIn("outcome", meta)
        self.assertIn("start_epoch", meta)
        self.assertEqual(meta["host_id"], field.host_id())
        pid = meta["pid"]
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        plan = self.plan()
        self.assertEqual(plan["action"], "collect", plan)
        self.assertNotIn("force-spawn", json.dumps(plan))
        text = self.ok("resume").stdout
        self.assertNotIn("MISSING", text)
        self.assertIn("orphan_settled", text)
        self.ok("collect")
        self.assertEqual(json.loads(record.read_text())["outcome"], "orphan_settled")
        self.assertEqual(self.plan()["action"], "integrate")

    def test_fresh_pidless_record_is_a_launch_not_an_orphan(self) -> None:
        # claim_started drops field.lock before run_child stamps the pid.
        self.pack("ex1")
        self.residual("ex1")  # prior valid residual of a continuation spawn
        record = self.spawn_record("ex1", {})
        plan = self.plan()
        self.assertEqual((plan["action"], plan["reason_code"]), ("hold", "live_spawn"))
        self.ok("checkpoint", "--summary", "concurrent writer")  # runs settle_orphans
        self.assertNotIn("outcome", json.loads(record.read_text()))
        meta = json.loads(record.read_text())
        meta["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 120))
        record.write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(self.plan()["action"], "collect")  # past the grace: orphan

    # -- D5: truncated residual ------------------------------------------
    def test_truncated_residual_is_repair_not_collect(self) -> None:
        packet = self.pack("ex1")
        path = self.residual("ex1")
        path.write_bytes(path.read_bytes()[:40])
        plan = self.plan()
        self.assertEqual((plan["action"], plan["reason_code"]), ("repair", "invalid_residual"))
        self.assertEqual([t["child_id"] for t in plan["targets"]], ["ex1"])
        self.assertEqual(plan["targets"][0]["argv"], ["of", "spawn", "--packet", packet])
        self.assertIn("invalid JSON", plan["detail"])
        text = self.ok("resume").stdout
        self.assertIn("next\n  REPAIR", text)
        self.assertIn("residual    INVALID", text)
        self.assertEqual(run_of(self.tmp, "collect").returncode, 2)
        self.assertEqual(self.plan()["action"], "repair")  # never loops on COLLECT
        checked = run_of(self.tmp, "validate", "--packet", packet, str(path))
        self.assertEqual(checked.returncode, 2, checked.stdout)
        self.assertIn("INVALID", checked.stdout)

    def test_validate_packet_runs_the_collect_gate(self) -> None:
        packet = self.pack("ex1")
        path = self.residual("ex1")
        good = self.ok("validate", "--packet", packet, str(path))
        self.assertIn("collect gate", good.stdout)
        data = json.loads(path.read_text())
        data["order_rev"] = 99  # schema-valid, wrong packet binding
        path.write_text(json.dumps(data), encoding="utf-8")
        self.ok("validate", "--kind", "residual", str(path))
        bound = run_of(self.tmp, "validate", "--packet", packet, str(path))
        self.assertEqual(bound.returncode, 2)
        self.assertIn("order_rev", bound.stdout)

    # -- D6: duplicate writer --------------------------------------------
    def test_handoff_claim_is_excluded_from_spawn_targets(self) -> None:
        claimed = self.pack("ex1")
        free = self.pack("ex2")
        self.ok("handoff", "--packet", claimed)
        plan = self.plan()
        self.assertEqual(plan["action"], "spawn")
        self.assertEqual(plan["targets"], [
            {"child_id": "ex2", "packet": free, "argv": ["of", "spawn", "--packet", free]},
        ])
        status = json.loads(self.ok("status", "--json").stdout)["next_plan"]
        self.assertEqual([t["child_id"] for t in status["targets"]], ["ex2"])
        self.assertEqual(status["inputs_digest"], plan["inputs_digest"])

    def test_unclaimed_scratch_never_expires_by_packed_at(self) -> None:
        import of as ofmod

        self.pack("w")
        old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        ofmod.PackedAge.backdate_packet(self.tmp, "w", old)
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "w"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "notes.md").write_text("a native child is writing this now\n", encoding="utf-8")
        plan = self.plan()
        self.assertEqual((plan["action"], plan["reason_code"]), ("hold", "scratch_unclaimed"))
        self.assertEqual(plan["targets"][0]["argv"], [])
        (scratch / "PULSE").write_text(f"{old} started\n", encoding="utf-8")
        self.assertEqual(self.plan()["reason_code"], "scratch_unclaimed")  # stale beat: still HOLD

    def test_expired_claim_is_extended_by_a_fresh_heartbeat(self) -> None:
        packet = self.pack("w")
        self.ok("handoff", "--packet", packet)
        claim = self.tmp / ".orderfield" / "waves" / "001" / "claims" / "w.json"
        doc = json.loads(claim.read_text())
        hour_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        doc["lease_expires"] = hour_ago
        claim.write_text(json.dumps(doc), encoding="utf-8")
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "w"
        scratch.mkdir(parents=True, exist_ok=True)
        pulse = scratch / "PULSE"
        pulse.write_text(f"{hour_ago} started\n{field.utc_now()} running the suite\n", encoding="utf-8")
        plan = self.plan()
        self.assertEqual((plan["action"], plan["reason_code"]), ("hold", "claimed"))
        self.assertEqual(plan["targets"][0]["argv"], [])
        pulse.write_text(f"{hour_ago} started\n{{\"type\":\"stream\"}}\n", encoding="utf-8")
        plan = self.plan()
        self.assertEqual((plan["action"], plan["reason_code"]), ("handoff", "lease_expired"))
        self.assertEqual(plan["targets"][0]["argv"], ["of", "handoff", "--packet", packet])

    def test_liveness_survives_tz_and_locale(self) -> None:
        meta: dict = {"child_id": "me"}
        path = self.tmp / "spawn.json"
        field.SpawnRecord.stamp_pid(path, meta, os.getpid())
        legacy = subprocess.run(
            ["ps", "-p", str(os.getpid()), "-o", "lstart="], capture_output=True, text=True,
            env={**os.environ, "TZ": "Asia/Tokyo", "LC_ALL": "C"},
        ).stdout.strip()
        probe = (
            "import json, sys; sys.path.insert(0, %r); import of.field as f; "
            "m = json.loads(sys.argv[1]); legacy = {'pid': m['pid'], 'starttime': sys.argv[2]}; "
            "print(f.SpawnRecord.liveness(m), f.SpawnRecord.liveness(legacy))" % str(SCRIPTS)
        )
        for env in ({"TZ": "UTC"}, {"TZ": "Asia/Tokyo"}, {"LC_ALL": "de_DE.UTF-8", "LANG": "de_DE.UTF-8"}):
            out = subprocess.run(
                [sys.executable, "-c", probe, json.dumps(meta), legacy],
                capture_output=True, text=True, env={**os.environ, **env},
            )
            new, old = out.stdout.split()
            self.assertEqual(new, "alive", (env, out.stderr))
            self.assertNotEqual(old, "dead", (env, legacy))
        foreign = {**meta, "host_id": "0" * 16}
        self.assertEqual(field.SpawnRecord.liveness(foreign), "unknown")
        self.assertEqual(field.SpawnRecord.liveness({"pid": self.dead_pid()}), "dead")

    def test_foreign_host_spawn_is_hold_unknown_never_force(self) -> None:
        self.pack("ex1")
        self.spawn_record("ex1", {"pid": os.getpid(), "host_id": "f" * 16, "start_epoch": 1})
        plan = self.plan()
        self.assertEqual((plan["action"], plan["reason_code"]), ("hold", "liveness_unknown"))
        self.assertEqual(plan["targets"][0]["argv"], [])

    def test_dead_started_only_names_force_spawn_target(self) -> None:
        packet = self.pack("ex1")
        self.spawn_record("ex1", {"pid": self.dead_pid(), "host_id": field.host_id(), "start_epoch": 1})
        plan = self.plan()
        self.assertEqual((plan["action"], plan["reason_code"]), ("hold", "dead_started_only"))
        self.assertEqual(plan["detail"], field.DeadStartedOnly.DETAIL)
        self.assertEqual(plan["targets"][0]["argv"][:4], ["of", "spawn", "--packet", packet])
        self.assertIn("--force-spawn", plan["targets"][0]["argv"])

    # -- D13: next is a function of disk ---------------------------------
    def test_scratch_mtime_does_not_move_next(self) -> None:
        self.pack("ex1")
        scratch = self.tmp / ".orderfield" / "work" / "scratch" / "ex1"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "PULSE").write_text("working\n", encoding="utf-8")
        before = self.plan()
        self.assertEqual((before["action"], before["reason_code"]), ("hold", "scratch_unclaimed"))
        old = time.time() - 30 * 24 * 3600
        os.utime(scratch / "PULSE", (old, old))
        os.utime(scratch, (old, old))
        after = self.plan()
        self.assertEqual(
            (after["action"], after["targets"], after["inputs_digest"]),
            (before["action"], before["targets"], before["inputs_digest"]),
        )
        text = self.ok("resume").stdout
        self.assertIn("continue existing packets; do not repack", text)
        self.assertIn(f"digest      {after['inputs_digest']}", text)

    def test_copytree_without_metadata_same_next(self) -> None:
        self.pack("ex1")
        self.pack("ex2")
        self.residual("ex1")
        bad = self.residual("ex2")
        bad.write_bytes(bad.read_bytes()[:30])
        copy = self.tmp.parent / f"{self.tmp.name}-copy"
        shutil.copytree(self.tmp, copy, copy_function=shutil.copyfile)
        self.addCleanup(shutil.rmtree, copy, True)
        a, b = self.plan(), self.plan(cwd=copy)
        self.assertEqual(a["action"], "repair")
        for key in ("action", "reason_code", "label", "detail", "targets", "inputs_digest"):
            self.assertEqual(a[key], b[key], key)

    def test_resume_never_writes(self) -> None:
        self.pack("ex1")
        self.pack("ex2")
        self.residual("ex1")
        self.spawn_record("ex1", {"pid": self.dead_pid(), "host_id": field.host_id(), "start_epoch": 1})
        stamp = self.tmp / ".orderfield" / "gc-stamp.json"
        stamp.write_text(json.dumps({"at": "2001-01-01T00:00:00Z"}), encoding="utf-8")
        before = tree_bytes(self.tmp)
        env = {"OF_NO_GC_AUTO": "0"}
        self.ok("resume", env=env)
        self.assertEqual(self.plan(env=env)["repaired"], [])
        self.ok("status", env=env)
        self.assertEqual(tree_bytes(self.tmp), before)

    def test_resume_writes_only_the_said_crash_repair(self) -> None:
        """The one exception: a crash after the CURRENT flip left live stale.
        resume restores exactly those files from CURRENT and says so."""
        self.pack("ex1")
        crashed = run_of(self.tmp, "patch", "--mission", "after crash",
                         env={"OF_WAL_CRASH": "after-current"})
        self.assertNotEqual(crashed.returncode, 0)
        before = tree_bytes(self.tmp)
        plan = self.plan()
        self.assertIn("ORDER.json", plan["repaired"])
        after = tree_bytes(self.tmp)
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        self.assertEqual(
            changed,
            sorted([f".orderfield/{r}" for r in plan["repaired"]] + [".orderfield/wal/MATERIALIZED.json"]),
        )
        self.assertNotIn("repaired live", self.ok("resume").stdout)  # once only
        self.assertEqual(tree_bytes(self.tmp), after)
        crashed = run_of(self.tmp, "patch", "--mission", "again",
                         env={"OF_WAL_CRASH": "after-current"})
        self.assertNotEqual(crashed.returncode, 0)
        self.assertIn("repaired live from CURRENT (crash after commit): ORDER.json",
                      self.ok("resume").stdout)

    # -- D8: read-side tamper --------------------------------------------
    def test_live_order_tamper_is_restore_and_from_current_fixes(self) -> None:
        order = self.tmp / ".orderfield" / "ORDER.json"
        good = order.read_bytes()
        data = json.loads(good)
        data["mission"] = "hijacked"
        order.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        plan = self.plan()
        self.assertEqual((plan["action"], plan["drift"]), ("restore", ["ORDER.json"]))
        self.assertEqual(plan["targets"][0]["argv"], ["of", "patch", "--from-current"])
        text = self.ok("resume").stdout
        self.assertIn("LIVE!=CURRENT ORDER.json", text)
        self.assertIn("next\n  RESTORE", text)
        self.assertIn("LIVE!=CURRENT ORDER.json", self.ok("status").stdout)
        self.assertIn("LIVE!=CURRENT ORDER.json", run_of(self.tmp, "doctor").stdout)
        self.assertNotEqual(run_of(self.tmp, "patch", "--constraints-add", "x").returncode, 0)
        child = run_of(self.tmp, "patch", "--from-current", env={"OF_CHILD": "ex1"})
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("hijacked", order.read_text())
        fixed = self.ok("patch", "--from-current")
        self.assertIn("restored      ORDER.json", fixed.stdout)
        self.assertEqual(order.read_bytes(), good)
        kept = list((self.tmp / ".orderfield" / "wal" / "orphans").rglob("ORDER.json"))
        self.assertTrue(kept and "hijacked" in kept[0].read_text(), kept)
        self.assertEqual(self.plan()["drift"], [])
        self.ok("patch", "--constraints-add", "after restore")

    # -- INT-06: forged close ---------------------------------------------
    def test_planted_packet_is_restore_and_handoff_refuses(self) -> None:
        packet = self.pack("ex1")
        packets = self.tmp / ".orderfield" / "waves" / "001" / "packets"
        live = packets / "ex1.json"
        good = live.read_bytes()
        live.write_text(json.dumps(json.loads(good)), encoding="utf-8")  # rewritten live
        plan = self.plan()
        self.assertEqual((plan["action"], plan["targets"][0]["argv"]),
                         ("restore", ["of", "patch", "--from-current"]))
        refused = run_of(self.tmp, "handoff", "--packet", packet)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("waves/001/packets/ex1.json", refused.stderr)
        mixed = run_of(self.tmp, "patch", "--from-current", "--mission", "x")
        self.assertNotEqual(mixed.returncode, 0)
        self.assertIn("no other patch flags", mixed.stderr)
        self.ok("patch", "--from-current")
        self.assertEqual(live.read_bytes(), good)
        self.assertNotEqual(self.plan()["action"], "restore")
        self.ok("handoff", "--packet", packet)

    def test_forged_spec_closed_keeps_auto_continue(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        code = (
            "import sys; sys.path.insert(0, %r); from pathlib import Path; import of.field as f\n"
            "root = Path(sys.argv[1])\n"
            "with f.field_lock(root, 'patch'):\n"
            "    o = f.load_order(root); o['spec_closed'] = True; f.save_order(o, root)\n"
        ) % str(SCRIPTS)
        subprocess.run([sys.executable, "-c", code, str(self.tmp)], check=True,
                       env={**os.environ, "OF_NO_UPDATE_CHECK": "1"})
        plan = self.plan()
        self.assertEqual(plan["auto_continue"], "yes")
        self.assertEqual((plan["action"], plan["reason_code"]), ("close-unproven", "close_unproven"))
        self.assertIn("CLOSE.json absent", plan["detail"])
        text = self.ok("resume").stdout
        self.assertIn("auto_continue yes", text)
        self.assertIn("field         open (spec_closed does not verify)", text)

    # -- D9: ACTIVE ---------------------------------------------------------
    def test_active_is_not_moved_by_reads_and_writers_need_a_field(self) -> None:
        first = json.loads((self.tmp / ".orderfield" / "ORDER.json").read_text())["id"]
        self.ok("new", "--mission", "second epic")
        active = self.tmp / ".orderfield" / "ACTIVE"
        second = active.read_text().strip()
        self.assertNotEqual(first, second)
        before = active.read_bytes()
        self.ok("status", env={"OF_FIELD": first})
        self.ok("--field", first, "resume")
        self.assertEqual(active.read_bytes(), before)
        bound = self.ok("patch", "--constraints-add", "y")  # default: ACTIVE, named
        self.assertIn(f"field={second} bound_by=ACTIVE", bound.stderr)
        refused = run_of(self.tmp, "patch", "--constraints-add", "x", env={"OF_FIELD_STRICT": "1"})
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("needs --field", refused.stderr)
        wrote = self.ok("patch", "--constraints-add", "x", env={"OF_FIELD": first})
        self.assertIn(f"field={first}", wrote.stderr)
        self.assertEqual(active.read_bytes(), before)
        self.ok("fields", "--use", first)
        self.assertEqual(active.read_text().strip(), first)
        self.assertNotEqual(run_of(self.tmp, "fields", "--use", first, env={"OF_CHILD": "x"}).returncode, 0)

    def test_nested_layout_resume_from_root_and_subdir(self) -> None:
        self.ok("new", "--mission", "nested epic")
        self.assertFalse((self.tmp / ".orderfield" / "ORDER.json").exists())
        active = (self.tmp / ".orderfield" / "ACTIVE").read_text().strip()
        sub = self.tmp / "src" / "deep"
        sub.mkdir(parents=True)
        for cwd in (self.tmp, sub):
            out = self.ok("resume", cwd=cwd).stdout
            self.assertIn(f"id            {active}", out)
            self.assertIn("nested epic", out)


if __name__ == "__main__":
    unittest.main()
