#!/usr/bin/env python3
"""Re-audit gaps (KFINAL): each attack is a field in a temp git tree.

ScopeWrite per attempt (an obedient driver reaches INTEGRATE after the leader
reverts; an unreverted write is never laundered by a re-run), ScopeWrite
blind spots (.git/hooks, .git/config, ignored files), Unclaimed sibling
residuals, a v1 CLOSE.json downgrade in a chained generation, a planted green
check. Children are the generic fake adapter (OF_AGENT).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import run_of  # noqa: E402

WAVE = ".orderfield/waves/001"

# FAKE_MODE: "rel=text,..." product writes. FAKE_FORGE: a sibling id whose
# residual this child also writes (identity read from that packet).
AGENT = r'''#!{python}
import hashlib, json, os, pathlib, subprocess
root = pathlib.Path.cwd()
wt = os.environ.get("FAKE_BRANCH_WT", "")
if wt:
    subprocess.check_call(["git", "-C", wt, "config", "branch.demo-354.remote", "origin"])
pdir = root / ".orderfield/waves/001/packets"
def land(kid, note):
    pkt = json.loads((pdir / (kid + ".json")).read_text())
    owns = pkt.get("owns_paths") or []
    if owns:
        result = root / owns[0]
    else:
        result = root / pkt["scratch_dir"] / "notes.md"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(note + "\n")
    rel = str(result.relative_to(root))
    ev = "mapped " + rel + "\nartifact_sha: " + hashlib.sha256(result.read_bytes()).hexdigest()
    if owns:
        ev += "\nrollback: git checkout -- " + owns[0]
    res = {k: pkt[k] for k in ("packet_id", "packet_hash", "order_id", "order_rev", "wave", "child_id", "role")}
    res.update(status="done", result_ref=rel,
               residual={"wants_to_change": [], "evidence": ev, "proposed_patch": None},
               metrics={"uncertainty": 0.1, "divergence": 0.0, "tool_failures": 0, "novelty": False})
    out = root / pkt["residual_path"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res))
for spec in filter(None, os.environ.get("FAKE_MODE", "").split(",")):
    rel, _, text = spec.partition("=")
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text + "\n")
if os.environ.get("FAKE_FORGE"):
    land(os.environ["FAKE_FORGE"], "forged by " + os.environ["OF_CHILD"])
land(os.environ["OF_CHILD"], "mapped " + os.environ["OF_CHILD"])
'''


class Field:
    def __init__(self, test: unittest.TestCase, gitignore: str = "") -> None:
        self.test = test
        self.tmp = Path(tempfile.mkdtemp(prefix="of-kfinal-"))
        aux = Path(tempfile.mkdtemp(prefix="of-kfinal-aux-"))
        test.addCleanup(shutil.rmtree, self.tmp, True)
        test.addCleanup(shutil.rmtree, aux, True)
        self.agent = aux / "agent.py"
        self.agent.write_text(AGENT.replace("{python}", sys.executable), encoding="utf-8")
        self.agent.chmod(0o755)
        for rel, text in (("README.md", "readme\n"), ("src/app.py", "print(1)\n"),
                          ("a.txt", "alpha\n"), (".gitignore", gitignore)):
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / rel).write_text(text, encoding="utf-8")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.ok("init", "--mission", "m", "--phase", "build", "--agent-band", "10-50")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "user.email=k@example.invalid", "-c", "user.name=k",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=self.tmp, check=True, capture_output=True)

    def of(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return run_of(self.tmp, *args, env=env, timeout=120)

    def ok(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        r = self.of(*args, **env)
        self.test.assertEqual(r.returncode, 0, f"of {' '.join(args)}\n{r.stdout}\n{r.stderr}")
        return r

    def pack(self, child: str, role: str = "explorer", *owns: str, req: str = "") -> None:
        flags = [x for p in owns for x in ("--owns-path", p)]
        flags += ["--owns-requirement", req] if req else []
        self.ok("pack", "--slice", f"slice {child}", "--role", role, "--child-id", child,
                *flags, "--force")

    def child_env(self, mode: str = "", forge: str = "") -> dict[str, str]:
        return {"OF_AGENT": str(self.agent), "OF_SPAWN_ENV": "FAKE_MODE,FAKE_FORGE,FAKE_BRANCH_WT",
                "FAKE_MODE": mode, "FAKE_FORGE": forge, "FAKE_BRANCH_WT": ""}

    def spawn(self, child: str, mode: str = "", forge: str = "", *extra: str):
        return self.ok("spawn", "--adapter", "generic", "--packet",
                       f"{WAVE}/packets/{child}.json", *extra, **self.child_env(mode, forge))

    def plan(self) -> dict:
        return json.loads(self.ok("resume", "--json").stdout)

    def validate(self, child: str) -> subprocess.CompletedProcess[str]:
        return self.of("validate", "--packet", f"{WAVE}/packets/{child}.json",
                       f"{WAVE}/residuals/{child}.json")


class ScopeWriteAttempts(unittest.TestCase):
    """Next and its mutators judge the same current ScopeWrite verdict."""

    def violate(self) -> Field:
        field = Field(self)
        field.pack("i1", "implementer", "src/app.py")
        field.spawn("i1", "src/app.py=print(2),README.md=hijack")
        return field

    def test_resume_validate_collect_agree_before_collect(self) -> None:
        field = self.violate()
        plan = field.plan()  # spawn exit froze the changed set: no collect needed
        self.assertEqual((plan["action"], plan["reason_code"]), ("repair", "invalid_residual"))
        self.assertIn("rule=ScopeWrite", plan["detail"])
        self.assertEqual(field.validate("i1").returncode, 2)
        self.assertEqual(field.of("collect").returncode, 2)

    def test_obedient_driver_reaches_integrate_after_revert(self) -> None:
        field = self.violate()
        field.of("collect")
        trace: list[str] = []
        for _step in range(6):
            plan = field.plan()
            trace.append(f"{plan['action']}:{plan['reason_code']}")
            if plan["action"] == "integrate":
                break
            if "rule=ScopeWrite" in plan["detail"]:
                field.git("checkout", "--", "README.md")  # the leader act the detail names
            argv = plan["targets"][0]["argv"][1:]
            env: dict[str, str] = {}
            if argv[0] == "spawn":
                argv += ["--adapter", "generic"]
                env = field.child_env("src/app.py=print(3)")
            r = field.of(*argv, **env)
            trace[-1] += f" -> {' '.join(argv[:2])}={r.returncode}"
            if argv[0] != "collect":
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                # Between attempts every reader agrees with what collect will say.
                if argv[0] == "spawn":
                    self.assertEqual(field.validate("i1").returncode, 0, trace)
        self.assertEqual(trace[-1].split(" ")[0], "integrate:collected", trace)
        self.assertLessEqual(len(trace), 4, trace)
        field.ok("integrate", "--wave", "1")

    def test_unreverted_write_survives_a_re_run(self) -> None:
        field = self.violate()
        field.spawn("i1", "src/app.py=print(3)")  # obedient re-run, nothing reverted
        plan = field.plan()
        self.assertEqual(plan["action"], "repair")
        self.assertIn("README.md", plan["detail"])
        self.assertEqual(field.validate("i1").returncode, 2)
        self.assertEqual(field.of("collect").returncode, 2)

    def test_leader_edit_between_attempts_is_not_the_child(self) -> None:
        field = self.violate()
        field.git("checkout", "--", "README.md")
        (field.tmp / "a.txt").write_text("leader edit\n", encoding="utf-8")
        field.spawn("i1", "src/app.py=print(3)")
        self.assertEqual(field.validate("i1").returncode, 0)
        self.assertIn("ok=1", field.ok("collect").stdout)

    def handoff_hijack(self) -> Field:
        field = Field(self)
        field.pack("e1")
        field.ok("handoff", "--packet", f"{WAVE}/packets/e1.json")
        (field.tmp / "README.md").write_text("hijack\n", encoding="utf-8")
        return field

    def land_and_collect(self, field: Field) -> None:
        subprocess.run([sys.executable, str(field.agent)], cwd=field.tmp, check=True,
                       env={"OF_CHILD": "e1", "PATH": "/usr/bin:/bin"})
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        line = next(x for x in r.stdout.splitlines() if "rule=ScopeWrite" in x)
        self.assertIn("README.md", line)

    def test_printed_handoff_after_lease_expiry_does_not_launder(self) -> None:
        field = self.handoff_hijack()
        claim = field.tmp / WAVE / "claims/e1.json"
        doc = json.loads(claim.read_text())
        doc["lease_expires"] = "2000-01-01T00:00:00Z"
        claim.write_text(json.dumps(doc), encoding="utf-8")
        plan = field.plan()
        self.assertEqual((plan["action"], plan["reason_code"]), ("handoff", "lease_expired"))
        field.ok(*plan["targets"][0]["argv"][1:])  # the obedient driver
        self.land_and_collect(field)

    def test_second_handoff_does_not_launder(self) -> None:
        field = self.handoff_hijack()
        field.of("handoff", "--packet", f"{WAVE}/packets/e1.json")
        field.of("handoff", "--packet", f"{WAVE}/packets/e1.json", "--force")
        self.land_and_collect(field)


class ScopeWriteBlindSpots(unittest.TestCase):
    def collect_line(self, field: Field) -> str:
        r = field.of("collect")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        return next(x for x in r.stdout.splitlines() if "rule=ScopeWrite" in x)

    def test_git_hook_and_config_writes_are_seen(self) -> None:
        field = Field(self)
        field.pack("i1", "implementer", "src/app.py")
        field.spawn("i1", "src/app.py=print(2),.git/hooks/pre-commit=echo pwned")
        self.assertIn(".git/hooks/pre-commit", self.collect_line(field))
        field = Field(self)
        field.pack("e1")
        cfg = (field.tmp / ".git/config").read_text(encoding="utf-8")
        field.spawn("e1", ".git/config=" + cfg + "[core]\n\thooksPath = /tmp/x")
        self.assertIn(".git/config", self.collect_line(field))

    def test_child_that_breaks_git_fails_closed(self) -> None:
        field = Field(self)
        field.pack("e1")
        field.spawn("e1", ".git/config=[[[ not a config")
        self.assertIn("git tree unreadable after this run", self.collect_line(field))

    def test_other_worktree_branch_section_is_not_scopewrite(self) -> None:
        field = Field(self)
        other = field.tmp.parent / (field.tmp.name + "-wt")
        field.git("worktree", "add", "-q", str(other), "HEAD")
        self.addCleanup(shutil.rmtree, other, True)
        field.pack("i1", "implementer", "src/app.py")
        env = field.child_env("src/app.py=print(2)")
        env["FAKE_BRANCH_WT"] = str(other)
        field.ok("spawn", "--adapter", "generic", "--packet", f"{WAVE}/packets/i1.json", **env)
        cfg = (field.tmp / ".git/config").read_text(encoding="utf-8")
        self.assertIn('[branch "demo-354"]', cfg)
        r = field.ok("collect")
        self.assertNotIn(".git/config", r.stdout)
        self.assertIn("ok=1", r.stdout)

    def test_revert_names_unrevertible_git_and_dirty_baseline(self) -> None:
        field = Field(self)
        field.pack("i1", "implementer", "src/app.py")
        (field.tmp / "README.md").write_text("dirty baseline\n", encoding="utf-8")
        cfg = (field.tmp / ".git/config").read_text(encoding="utf-8")
        field.spawn(
            "i1",
            "src/app.py=print(2),README.md=child hijack,.git/config="
            + cfg
            + "[core]\n\thooksPath = /tmp/x",
        )
        bare = field.of("collect")
        self.assertEqual(bare.returncode, 2, bare.stdout + bare.stderr)
        line = next(x for x in bare.stdout.splitlines() if "rule=ScopeWrite" in x)
        self.assertIn("nothing to revert", line)
        self.assertIn(".git/config", line)
        self.assertIn("README.md", line)
        self.assertIn(".git/ excluded", line)
        self.assertIn("baseline already dirty", line)
        flagged = field.of("collect", "--revert-out-of-scope")
        self.assertEqual(flagged.returncode, 2, flagged.stdout + flagged.stderr)
        self.assertIn("skipped     i1: .git/config (.git/ excluded)", flagged.stdout)
        self.assertIn("skipped     i1: README.md (baseline already dirty)", flagged.stdout)
        self.assertNotIn("quarantined", flagged.stdout)
        self.assertEqual((field.tmp / "README.md").read_text(encoding="utf-8"), "child hijack\n")
        self.assertIn("hooksPath", (field.tmp / ".git/config").read_text(encoding="utf-8"))

    def test_ignored_file_is_seen_heavy_dirs_are_not(self) -> None:
        field = Field(self, gitignore=".env\nnode_modules/\nlogs/\n")
        field.pack("i1", "implementer", "src/app.py")
        field.spawn("i1", "src/app.py=print(2),.env=API_KEY=attacker,"
                          "node_modules/x/index.js=1,logs/deep/run.log=x")
        line = self.collect_line(field)
        self.assertIn(".env", line)
        self.assertIn("logs/deep/run.log", line)
        self.assertNotIn("node_modules", line)

    def test_path_with_paren_is_reverted_whole(self) -> None:
        field = Field(self)
        field.pack("i1", "implementer", "src/app.py")
        field.spawn("i1", "src/app.py=print(2),assets/Screenshot (1).png=x")
        self.assertIn("assets/Screenshot (1).png", self.collect_line(field))
        r = field.ok("collect", "--revert-out-of-scope")
        self.assertIn("reverted 1 out-of-scope path(s)", r.stdout)
        self.assertFalse((field.tmp / "assets/Screenshot (1).png").exists())

    def test_code_running_config_key_is_seen(self) -> None:
        field = Field(self)
        field.pack("e1")
        cfg = (field.tmp / ".git/config").read_text(encoding="utf-8")
        field.spawn("e1", ".git/config=" + cfg + "[alias]\n\tst = !touch /tmp/pwned")
        self.assertIn(".git/config", self.collect_line(field))

    def test_global_config_edit_is_not_the_childs(self) -> None:
        from _harness import hermetic_env

        gitconfig = Path(hermetic_env()["HOME"]) / ".gitconfig"
        self.addCleanup(gitconfig.unlink, True)
        field = Field(self)
        field.pack("i1", "implementer", "src/app.py")
        field.spawn("i1", f"src/app.py=print(2),{gitconfig}=[core]\n\tsshCommand = ssh -v")
        self.assertIn("sshCommand", gitconfig.read_text(encoding="utf-8"))
        r = field.ok("collect")
        self.assertNotIn(".git/config", r.stdout)
        self.assertIn("ok=1", r.stdout)

    def test_failed_checkout_is_reported_not_dropped(self) -> None:
        field = Field(self)
        field.pack("i1", "implementer", "src/app.py")
        field.spawn("i1", "src/app.py=print(2),README.md=hijack")
        lock = field.tmp / ".git/index.lock"
        lock.write_text("", encoding="utf-8")
        self.addCleanup(lock.unlink, True)
        r = field.of("collect", "--revert-out-of-scope")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("README.md (git checkout failed", r.stdout)
        self.assertEqual((field.tmp / "README.md").read_text(encoding="utf-8"), "hijack\n")

    def test_ignored_tool_output_is_not_a_write(self) -> None:
        field = Field(self, gitignore="*.egg-info/\n.DS_Store\nhtmlcov/\n")
        field.pack("i1", "implementer", "src/app.py")
        field.spawn("i1", "src/app.py=print(2),app.egg-info/PKG-INFO=x,.DS_Store=x,"
                          "src/.DS_Store=x,htmlcov/index.html=x")
        self.assertIn("ok=1", field.ok("collect").stdout)


class ScopeWriteBaseline(unittest.TestCase):
    """Snapshot internals the CLI cannot reach: caps, old baselines, a
    baseline git could not answer."""

    def setUp(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        self.addCleanup(sys.path.remove, sys.path[0])
        from of.pack import ScopeWrite

        self.sw = ScopeWrite

    def test_hooks_are_watched_past_the_ignored_cap(self) -> None:
        from unittest import mock

        field = Field(self, gitignore="data/\n")
        for n in range(3):
            (field.tmp / f"data/f{n}.bin").parent.mkdir(exist_ok=True)
            (field.tmp / f"data/f{n}.bin").write_text(str(n), encoding="utf-8")
        (field.tmp / ".git/hooks/pre-commit").write_text("echo x\n", encoding="utf-8")
        with mock.patch.object(self.sw, "MAX_IGNORED", 1):
            snap = self.sw.snapshot(field.tmp)
        self.assertIn(".git/hooks/pre-commit", snap["dirty"])
        self.assertEqual(snap["capped"], 2)

    def test_pre_scheme_baseline_is_not_a_config_change(self) -> None:
        field = Field(self)
        after = self.sw.snapshot(field.tmp)
        cfg = self.sw.CONFIG
        legacy_file = self.sw._blob_id(field.tmp / ".git/config")  # 0.9.1
        legacy_all = self.sw._fingerprint(  # 0.9.2
            self.sw._config_lines(field.tmp, self.sw.LEGACY_CONFIG_KEYS) or []
        )
        for value in (legacy_file, legacy_all):
            before = {"head": after["head"], "dirty": {**after["dirty"], cfg: value}}
            self.assertEqual(self.sw.changed(field.tmp, before, after), [])
        before = {"head": after["head"], "dirty": {**after["dirty"], cfg: "0" * 40}}
        self.assertEqual(self.sw.changed(field.tmp, before, after), [cfg])

    def test_unreadable_baseline_fails_closed(self) -> None:
        from unittest import mock

        field = Field(self)
        field.pack("e1")
        packet = json.loads((field.tmp / WAVE / "packets/e1.json").read_text())
        with mock.patch.object(self.sw, "snapshot", return_value=None):
            self.sw.rebase(field.tmp, packet)
        doc = self.sw.load(field.tmp, packet)
        self.assertIsNone(doc["skip"])
        self.assertIsNone(self.sw.evaluate(field.tmp, packet, {}))
        errs = self.sw.errors(field.tmp, packet)
        self.assertEqual(len(errs), 1)
        self.assertIn("git tree unreadable at baseline", errs[0])


class UnclaimedSibling(unittest.TestCase):
    def test_sibling_forged_residual_is_unclaimed_until_accepted(self) -> None:
        field = Field(self)
        field.pack("c1")
        field.pack("c2")
        field.spawn("c1", forge="c2")
        plan = field.plan()
        self.assertEqual(plan["action"], "repair")
        self.assertIn("c2: rule=Unclaimed", plan["detail"])
        self.assertEqual(field.validate("c2").returncode, 2)
        r = field.of("collect")
        self.assertEqual(r.returncode, 2)
        self.assertIn("INVALID c2.json: rule=Unclaimed", r.stdout)
        self.assertIn("OK c1.json", r.stdout)
        r = field.ok("collect", "--accept-unclaimed", "c2")
        self.assertIn("ok=2", r.stdout)
        self.assertEqual(field.validate("c2").returncode, 0)

    def test_handoff_claimed_residual_collects(self) -> None:
        field = Field(self)
        field.pack("c1")
        field.pack("c2")
        field.ok("handoff", "--packet", f"{WAVE}/packets/c2.json")
        field.spawn("c1", forge="c2")  # bytes land where the claimed child writes
        self.assertIn("ok=2", field.ok("collect").stdout)

    def test_wave_without_spawn_or_claim_is_native(self) -> None:
        field = Field(self)
        field.pack("c1")
        field.pack("c2")
        for kid in ("c1", "c2"):
            subprocess.run([sys.executable, str(field.agent)], cwd=field.tmp, check=True,
                           env={"OF_CHILD": kid, "PATH": "/usr/bin:/bin"})
        self.assertIn("ok=2", field.ok("collect").stdout)

    def test_accepting_one_native_child_keeps_the_wave_native(self) -> None:
        field = Field(self)
        for kid in ("c1", "c2"):
            field.pack(kid)
        field.of("collect", "--accept-unclaimed", "c1")  # rc 2: both still missing
        for kid in ("c1", "c2"):
            subprocess.run([sys.executable, str(field.agent)], cwd=field.tmp, check=True,
                           env={"OF_CHILD": kid, "PATH": "/usr/bin:/bin"})
        self.assertIn("ok=2", field.ok("collect").stdout)


class ForgedState(unittest.TestCase):
    def forge_generation(self, field: Field, edit) -> None:
        """A complete, chain-valid child generation of CURRENT (a forger's best)."""
        wal = field.tmp / ".orderfield/wal"
        cur = json.loads((wal / "CURRENT.json").read_text())
        gid = f"{cur['seq'] + 1:08d}-f0f0f0f0f0f0"
        shutil.copytree(wal / cur["generation"], wal / gid)
        edit(wal / gid)
        man = json.loads((wal / gid / "MANIFEST.json").read_text())
        files = sorted({*man["files"], *(p.relative_to(wal / gid).as_posix()
                                         for p in (wal / gid).rglob("*") if p.is_file())} - {"MANIFEST.json"})
        man.update(generation=gid, seq=cur["seq"] + 1, parent=cur["generation"],
                   parent_manifest_sha256=cur["manifest_sha256"],
                   files={r: hashlib.sha256((wal / gid / r).read_bytes()).hexdigest() for r in files})
        man["order_sha256"] = man["files"]["ORDER.json"]
        (wal / gid / "MANIFEST.json").write_text(json.dumps(man))

    def test_chained_v1_close_does_not_close(self) -> None:
        field = Field(self)
        field.pack("e1")

        def closed(gen: Path) -> None:
            order = json.loads((gen / "ORDER.json").read_text())
            order.update(spec_closed=True, rev=order["rev"] + 1)
            (gen / "ORDER.json").write_text(json.dumps(order, indent=2))
            (gen / "CLOSE.json").write_text(json.dumps(
                {"v": 1, "verdict": "RESOLVED", "spec_closed": True, "order_id": order["id"],
                 "rev": order["rev"], "phase": order["phase"]}))

        self.forge_generation(field, closed)
        field.ok("checkpoint", "--summary", "leader touches the field")  # rolls it forward
        plan = field.plan()
        self.assertEqual(plan["auto_continue"], "yes")
        self.assertEqual(plan["action"], "close-unproven")
        self.assertIn("v1 is not the pre-chain close", plan["detail"])

    def test_planted_check_is_not_green(self) -> None:
        field = Field(self)
        field.ok("spec", "--add", "WID-001", "--text", "the widget prints hello")
        field.pack("i1", "implementer", "src/app.py", req="WID-001")
        field.spawn("i1", "src/app.py=print(2)")
        plant = field.tmp / ".orderfield/checks/WID-001.json"  # what the child also wrote
        plant.parent.mkdir(parents=True, exist_ok=True)
        plant.write_text(json.dumps({"id": "WID-001", "pass": True}), encoding="utf-8")
        self.assertNotIn("STOP", field.ok("resume").stdout)
        field.ok("collect")
        self.assertFalse((field.tmp / ".orderfield/checks/WID-001.json").exists(), "quarantined")
        quarantined = list((field.tmp / ".orderfield/wal/orphans").rglob("WID-001.json"))
        self.assertTrue(quarantined)
        refused = field.of("spec", "--verified-contract", "WID-001", "--cite", "src/app.py",
                           OF_CHILD="i1")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("child-forge", refused.stderr + refused.stdout)

    def test_leader_check_binds_its_cite(self) -> None:
        from_sys = sys.path[:]
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        try:
            from of.replay import DiscoveryReplay
            from of.wal import committed_bytes
        finally:
            sys.path[:] = from_sys
        field = Field(self)
        field.ok("spec", "--add", "WID-001", "--text", "the widget prints hello")
        (field.tmp / "surface.log").write_text("$ widget\nhello\n", encoding="utf-8")
        field.ok("spec", "--verified-contract", "WID-001", "--cite", "surface.log")
        self.assertIsNotNone(committed_bytes(field.tmp, "checks/WID-001.json"))
        self.assertTrue(DiscoveryReplay.externally_green(field.tmp, "WID-001"))
        (field.tmp / "surface.log").write_text("$ widget\nboom\n", encoding="utf-8")
        self.assertFalse(DiscoveryReplay.externally_green(field.tmp, "WID-001"))
        field.ok("spec", "--failed", "WID-001")
        self.assertIsNone(committed_bytes(field.tmp, "checks/WID-001.json"))


if __name__ == "__main__":
    unittest.main()
