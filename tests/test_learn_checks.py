#!/usr/bin/env python3
"""of learn --checks proposes; --accept is the write."""
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
from of.learn_checks import LearnChecks  # noqa: E402
from of.cli.field_cmd import _report_observations  # noqa: E402
import of  # noqa: E402

OF_PY = SCRIPTS / "of.py"
CONSTRAINT = "price_cli.py prints price table"


def run_of(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    base = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    base.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-learn-checks.json"),
    )
    for key in ("OF_CHILD", "OF_FIELD", "OF_ADAPTER", "OF_HANDOFF_CHILD"):
        base.pop(key, None)
    if env:
        base.update(env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=base,
        timeout=60,
    )


def product_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if ".orderfield" in path.parts or ".git" in path.parts:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def residual(evidence: str, *, constraint: str = CONSTRAINT, status: str = "threshold", failed: list[str] | None = None) -> dict:
    patch: dict = {}
    if constraint:
        patch["constraints+"] = [constraint]
    if failed:
        patch["requirements_failed"] = failed
    return {
        "status": status,
        "result_ref": "notes.md",
        "residual": {
            "wants_to_change": ["constraints"],
            "evidence": evidence,
            "proposed_patch": patch,
        },
        "metrics": {
            "uncertainty": 0.2,
            "divergence": 0.2,
            "tool_failures": 0,
            "novelty": False,
        },
    }


class GraduatedCheck(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.homes = [self.root / ".orderfield/fields" / fid for fid in ("ord_aaaaaaaa", "ord_bbbbbbbb")]
        self.home = self.homes[0]

    def plant(self, home, wave, body):
        path = home / f"waves/{wave:03d}/residuals/worker.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
        return path

    def graduate(self, body):
        history = {}
        for home in self.homes:
            path = self.plant(home, 1, body)
            history[path] = path.read_bytes()
            order = of.default_order("check prices", "build")
            order["id"] = home.name
            (home / "ORDER.json").write_text(json.dumps(order))
        claim, = LearnChecks.repeated(self.root)
        self.key = claim["key"]
        self.message = claim["message"]
        self.script = self.root / LearnChecks.script_rel(self.key)
        LearnChecks.accept(self.root, f"chk_{self.key}_check")
        self.assertIn(self.message, self.script.read_text())
        return history

    def check(self, expected):
        ran = subprocess.run([sys.executable, "-S", str(self.script)], cwd=self.root,
                             text=True, capture_output=True, timeout=10)
        self.assertEqual(ran.returncode, expected, ran.stderr)
        self.assertEqual(ran.stderr, self.message + "\n" if expected else "")

    def land(self, path, recompute=False):
        wave = path.parents[1]
        order = json.loads((self.home / "ORDER.json").read_text())
        residuals = [json.loads(path.read_text())]
        packets = [{"child_id": path.stem, "role": "verifier"}]
        failures = LearnChecks.landed_failures(order, residuals, packets)
        report = json.loads((wave / "report.json").read_text()) if recompute else None
        previously_failed = LearnChecks.carry_failures(failures, _report_observations(wave, report))
        with of.field.using_field_home(self.home):
            of.apply_requirement_patches(self.root, residuals, packets, previously_failed)
        key = ("b" if recompute else "a") * 64
        (wave / "integrations").mkdir(exist_ok=True)
        (wave / "integrations/observations.json").write_text(json.dumps({
            "wave": int(wave.name), "input_hash": key, "children": [], "learning_failures": failures,
        }))
        (wave / "report.json").write_text(json.dumps({"wave": int(wave.name), "integration": {"input_hash": key}}))

    def test_current_failure_fix_and_new_packet_with_history_intact(self):
        body = residual("same claim", constraint="", failed=["CLI-001"])
        history = self.graduate(body)
        ledger = self.home / "REQUIREMENTS.json"
        (self.home / "wal").mkdir()
        (self.home / "wal/CURRENT.json").write_text("{}")
        stamp = self.home / "checks/CLI-001.json"
        stamp.parent.mkdir()
        stamp.write_text(json.dumps({"id": "CLI-001", "pass": True}))

        def status(value):
            ledger.write_text(json.dumps({"v": 1, "spec_hash": "", "requirements": [{
                "id": "CLI-001", "text": "show the price table", "binding": True,
                "owned_by": [], "status": value,
            }]}))

        status("failed")
        self.check(1)
        status("verified_contract")
        self.check(0)
        for wave in (2, 3):
            path = self.plant(self.home, wave, {**body, "packet_id": f"pkt_{wave:032x}"})
            history[path] = path.read_bytes()
            self.check(1)
            newer = path.stat().st_mtime_ns + 2_000_000_000
            os.utime(ledger, ns=(newer, newer))
            os.utime(stamp, ns=(newer, newer))
            self.check(1)
            self.land(path)
            self.assertEqual(json.loads(ledger.read_text())["requirements"][0]["status"], "failed")
            self.check(1)
            status("verified_contract")
            self.check(0)
            self.land(path, recompute=True)
            self.assertEqual(json.loads(ledger.read_text())["requirements"][0]["status"], "verified_contract")
            self.check(0)
            os.utime(path, ns=(newer, newer))
            self.check(0)
        report = path.parents[1] / "report.json"
        integrated = json.loads(report.read_text())
        report.write_text(json.dumps({**integrated, "skipped_in_flight": ["worker"]}))
        self.check(1)
        report.write_text(json.dumps({**integrated, "integration": {"input_hash": "c" * 64}}))
        self.check(1)
        report.write_text(json.dumps(integrated))
        self.check(0)
        self.assertEqual(history, {p: p.read_bytes() for p in history})

    def test_constraints_recur_in_the_same_field_even_when_already_present(self):
        body = residual("constraint missing")
        history = self.graduate(body)
        self.check(1)
        order_path = self.home / "ORDER.json"
        order = json.loads(order_path.read_text())
        order["constraints"] = [CONSTRAINT]
        order_path.write_text(json.dumps(order))
        self.check(0)
        path = self.plant(self.home, 2, body)
        history[path] = path.read_bytes()
        self.land(path)
        self.check(1)
        LearnChecks.accept(self.root, f"chk_{self.key}_check")
        self.check(1)
        with of.field.using_field_home(self.home):
            LearnChecks.accept(self.root, f"chk_{self.key}_redesign")
            self.check(1)
            order["constraints"] = []
            order_path.write_text(json.dumps(order))
            LearnChecks.accept(self.root, f"chk_{self.key}_redesign")
        self.check(0)
        order["constraints"] = []
        order_path.write_text(json.dumps(order))
        path = self.plant(self.home, 3, body)
        history[path] = path.read_bytes()
        self.land(path)
        self.check(1)
        order["constraints"] = [CONSTRAINT]
        order_path.write_text(json.dumps(order))
        self.check(0)
        self.land(path, recompute=True)
        self.check(0)
        self.assertEqual(history, {p: p.read_bytes() for p in history})

    def test_phase_claim_can_recur_after_advance_with_history_intact(self):
        body = residual("cut is complete, advance to build", constraint="")
        body["residual"]["wants_to_change"] = ["phase"]
        history = self.graduate(body)
        self.check(0)
        for wave, home in enumerate(self.homes, 2):
            order_path = home / "ORDER.json"
            order = json.loads(order_path.read_text())
            order.update(phase="cut", rev=order["rev"] + 1)
            order_path.write_text(json.dumps(order))
            self.check(0)
            path = self.plant(home, wave, body)
            history[path] = path.read_bytes()
            self.check(1)
            LearnChecks.accept(self.root, f"chk_{self.key}_check")
            self.check(1)
            order.update(phase="build", rev=order["rev"] + 1)
            order_path.write_text(json.dumps(order))
            self.check(0)
            order["phase"] = "verify"
            order_path.write_text(json.dumps(order))
            self.check(0)
        self.assertEqual(history, {p: p.read_bytes() for p in history})

    def test_phase_suggestion_without_one_destination_is_prose(self):
        body = residual("advance to build, advance to verify", constraint="")
        body["residual"]["wants_to_change"] = ["phase"]
        for home in self.homes:
            self.plant(home, 1, body)
            (home / "ORDER.json").write_text(json.dumps(of.default_order("check prices", "cut")
                                                       | {"id": home.name}))
        self.assertEqual([row["kind"] for row in LearnChecks.proposals(self.root)], ["prose"])


class LearnChecksCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-learn-checks-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _ok(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args, env=env)
        self.assertEqual(proc.returncode, 0, f"{args}: {proc.stdout}{proc.stderr}")
        return proc

    def _fields(self) -> list[Path]:
        self._ok("init", "--mission", "show a price table", "--phase", "explore")
        self._ok("new", "--mission", "show the price table again")
        homes = sorted((self.tmp / ".orderfield" / "fields").glob("ord_*"))
        self.assertEqual(len(homes), 2, homes)
        return homes

    def _plant(self, home: Path, name: str, body: dict) -> None:
        dest = home / "waves" / "001" / "residuals" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(body) + "\n", encoding="utf-8")

    def _orders(self) -> list[Path]:
        return sorted((self.tmp / ".orderfield" / "fields").glob("ord_*/ORDER.json"))

    def _kinds(self, stdout: str) -> list[str]:
        return [line.split()[0] for line in stdout.splitlines() if line.strip()]

    def _messages(self, stdout: str) -> dict[str, str]:
        found: dict[str, str] = {}
        for line in stdout.splitlines():
            if not line.strip():
                continue
            kind = line[:12].strip()
            _ident, rest = line[12:].lstrip().split("  ", 1)
            _fields, message = rest.split("  ", 1)
            found[kind] = message
        return found

    def test_one_field_proposes_nothing_and_two_fields_are_ordered(self) -> None:
        homes = self._fields()
        self._plant(homes[0], "a.json", residual("missing from the first field"))
        alone = self._ok("learn", "--checks")
        self.assertEqual(alone.stdout.strip(), f"{'checks':12} none")
        self._plant(homes[0], "b.json", residual("same field, second file"))
        still = self._ok("learn", "--checks")
        self.assertEqual(still.stdout.strip(), f"{'checks':12} none")
        self._plant(homes[1], "c.json", residual("different wording, same claim"))
        before = product_digest(self.tmp)
        proposed = self._ok("learn", "--checks")
        self.assertEqual(product_digest(self.tmp), before)
        self.assertEqual(
            self._kinds(proposed.stdout),
            ["redesign", "check", "run", "prose"],
        )
        self.assertEqual(proposed.stdout.count("chk_"), 4)
        self.assertIn(f"add constraint {CONSTRAINT!r}", proposed.stdout)
        for home in homes:
            self.assertIn(home.name, proposed.stdout)
        self.assertFalse((self.tmp / "scripts").exists())
        self.assertFalse((self.tmp / "AGENTS.md").exists())

    def test_each_kind_names_its_own_action(self) -> None:
        homes = self._fields()
        self._plant(homes[0], "a.json", residual("one"))
        self._plant(homes[1], "b.json", residual("two"))
        proposed = self._ok("learn", "--checks")
        messages = self._messages(proposed.stdout)
        self.assertEqual(list(messages), ["redesign", "check", "run", "prose"])
        self.assertEqual(len(set(messages.values())), 4)
        key = next(
            line.split()[1]
            for line in proposed.stdout.splitlines()
            if line.startswith("check")
        ).split("_")[1]
        assertion = f"FAIL {key}: add constraint {CONSTRAINT!r}"
        command = f"`python3 scripts/checks/{key}.py`"
        self.assertEqual(messages["redesign"], f"fold into the plan: constraint {CONSTRAINT!r}")
        self.assertEqual(messages["check"], f"scripts/checks/{key}.py asserts {assertion}")
        self.assertEqual(
            messages["run"],
            f"feature-map row {key} reach {command}; done_when {command}",
        )
        self.assertEqual(messages["prose"], f"AGENTS.md: - add constraint {CONSTRAINT!r}")
        planted = json.loads((homes[0] / "waves" / "001" / "residuals" / "a.json").read_text(encoding="utf-8"))
        self.assertEqual(planted["residual"]["proposed_patch"]["constraints+"], [CONSTRAINT])

    def test_accept_check_names_the_fix_and_leaves_the_field(self) -> None:
        homes = self._fields()
        self._plant(homes[0], "a.json", residual("one"))
        self._plant(homes[1], "b.json", residual("two"))
        orders = [path.read_bytes() for path in self._orders()]
        feature = (self.tmp / ".orderfield" / "fields").glob("ord_*/feature-map.md")
        maps = {path: path.read_bytes() for path in feature}
        proposed = self._ok("learn", "--checks")
        check_id = next(
            line.split()[1]
            for line in proposed.stdout.splitlines()
            if line.startswith("check")
        )
        before = product_digest(self.tmp)
        self._ok("learn", "--checks")
        self.assertEqual(product_digest(self.tmp), before)
        accepted = self._ok("learn", "--accept", check_id)
        self.assertIn(check_id, accepted.stdout)
        self.assertEqual([path.read_bytes() for path in self._orders()], orders)
        for path, body in maps.items():
            self.assertEqual(path.read_bytes(), body)
        self.assertFalse((self.tmp / "AGENTS.md").exists())
        script = self.tmp / "scripts" / "checks" / f"{check_id.split('_')[1]}.py"
        self.assertTrue(script.is_file(), script)
        message = f"FAIL {check_id.split('_')[1]}: add constraint {CONSTRAINT!r}"
        self.assertIn(message, script.read_text(encoding="utf-8"))
        ran = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(ran.returncode, 1)
        self.assertEqual(ran.stderr.strip(), message)
        first = script.read_bytes()
        self._ok("learn", "--accept", check_id)
        self.assertEqual(script.read_bytes(), first)

    def test_accept_redesign_puts_the_constraint_in_the_contract(self) -> None:
        homes = self._fields()
        self._plant(homes[0], "a.json", residual("one"))
        self._plant(homes[1], "b.json", residual("two"))
        proposed = self._ok("learn", "--checks")
        redesign = next(line.split()[1] for line in proposed.stdout.splitlines() if line.startswith("redesign"))
        key = redesign.split("_")[1]
        before = {path: json.loads(path.read_text(encoding="utf-8")) for path in self._orders()}
        self._ok("learn", "--accept", redesign)
        after = {path: json.loads(path.read_text(encoding="utf-8")) for path in self._orders()}
        bumped = [
            path
            for path, order in after.items()
            if CONSTRAINT in order["constraints"] and CONSTRAINT not in before[path]["constraints"]
        ]
        self.assertEqual(len(bumped), 1, bumped)
        self.assertEqual(after[bumped[0]]["rev"], before[bumped[0]]["rev"] + 1)
        script = self.tmp / "scripts" / "checks" / f"{key}.py"
        ran = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(ran.returncode, 0, ran.stderr)
        rev = after[bumped[0]]["rev"]
        self._ok("learn", "--accept", redesign)
        again = json.loads(bumped[0].read_text(encoding="utf-8"))
        self.assertEqual(again["rev"], rev)
        self.assertEqual(again["constraints"].count(CONSTRAINT), 1)

    def test_accept_run_keeps_done_when_and_prose_is_one_line(self) -> None:
        homes = self._fields()
        self._plant(homes[0], "a.json", residual("one"))
        self._plant(homes[1], "b.json", residual("two"))
        proposed = self._ok("learn", "--checks")
        lines = {line.split()[0]: line.split()[1] for line in proposed.stdout.splitlines()}
        key = lines["run"].split("_")[1]
        command = f"`python3 scripts/checks/{key}.py`"
        self._ok("learn", "--accept", lines["run"])
        active = None
        for path in self._orders():
            order = json.loads(path.read_text(encoding="utf-8"))
            if command in order["done_when"]:
                active = order
                break
        self.assertIsNotNone(active)
        assert active is not None
        self.assertIn("of contrast RESOLVED then of close", active["done_when"])
        maps = list((self.tmp / ".orderfield" / "fields").glob("ord_*/feature-map.md"))
        blob = "\n".join(path.read_text(encoding="utf-8") for path in maps)
        self.assertIn(command, blob)
        self._ok("learn", "--accept", lines["prose"])
        agents = (self.tmp / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(f"add constraint {CONSTRAINT!r}"), 1)
        self._ok("learn", "--accept", lines["prose"])
        self.assertEqual((self.tmp / "AGENTS.md").read_text(encoding="utf-8"), agents)

    def test_a_different_claim_or_a_resolved_residual_proposes_nothing(self) -> None:
        homes = self._fields()
        self._plant(homes[0], "a.json", residual("one", constraint="alpha"))
        self._plant(homes[1], "b.json", residual("two", constraint="beta"))
        split = self._ok("learn", "--checks")
        self.assertEqual(split.stdout.strip(), f"{'checks':12} none")
        self._plant(homes[0], "a.json", residual("done", status="done", constraint=""))
        self._plant(homes[1], "b.json", residual("done too", status="done", constraint=""))
        done = self._ok("learn", "--checks")
        self.assertEqual(done.stdout.strip(), f"{'checks':12} none")

    def test_phase_proposal_and_generated_check_follow_the_local_phase(self) -> None:
        homes = self._fields()
        body = residual("change the phase", constraint="")
        body["residual"]["wants_to_change"] = ["phase"]
        for home in homes:
            self._plant(home, "phase.json", body)
        self.assertEqual(self._kinds(self._ok("learn", "--checks").stdout), ["prose"])

        body["residual"]["evidence"] = "cut is complete, advance to build"
        for home in homes:
            self._plant(home, "advance.json", body)
        proposals = self._ok("learn", "--checks").stdout
        self.assertEqual(self._kinds(proposals), ["check", "run", "prose"])
        check_id = proposals.splitlines()[0].split()[1]
        self._ok("learn", "--accept", check_id)
        script = self.tmp / LearnChecks.script_rel(check_id.split("_")[1])
        history = {p: p.read_bytes() for home in homes for p in home.glob("waves/*/residuals/*.json")}
        for home in homes:
            selected = ("--field", home.name)
            self._ok(*selected, "phase", "cut", "--force", "--reason", "price fixture needs a build")
            self._plant(home, "recurrence.json", body)
            path = home / "waves/001/residuals/recurrence.json"
            history[path] = path.read_bytes()
            red = subprocess.run([sys.executable, "-S", script], capture_output=True, text=True, timeout=10)
            self.assertEqual(red.returncode, 1, red.stderr)
            self._ok(*selected, "phase", "build", "--force", "--reason", "price fixture entered build")
            green = subprocess.run([sys.executable, "-S", script], capture_output=True, text=True, timeout=10)
            self.assertEqual(green.returncode, 0, green.stderr)
        self.assertEqual(history, {path: path.read_bytes() for path in history})

    def test_failed_requirement_starts_at_the_check(self) -> None:
        homes = self._fields()
        body = residual("wrong", status="done", constraint="", failed=["CLI-001"])
        self._plant(homes[0], "a.json", body)
        self._plant(homes[1], "b.json", {**body, "residual": {**body["residual"], "evidence": "other words"}})
        proposed = self._ok("learn", "--checks")
        self.assertEqual(self._kinds(proposed.stdout), ["check", "run", "prose"])
        self.assertIn("requirement 'CLI-001' is still failed", proposed.stdout)
        check_id = next(line.split()[1] for line in proposed.stdout.splitlines() if line.startswith("check"))
        self._ok("learn", "--accept", check_id)
        key = check_id.split("_")[1]
        script = self.tmp / "scripts" / "checks" / f"{key}.py"
        history = {path: path.read_bytes() for home in homes for path in home.glob("waves/*/residuals/*.json")}
        green = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=30)
        self.assertEqual(green.returncode, 0, green.stderr)
        selected = ("--field", homes[0].name)
        self._ok(*selected, "spec", "--add", "CLI-001", "--text", "show a price table")
        self._ok(*selected, "pack", "--child-id", "recurrence", "--role", "verifier",
                 "--owns-requirement", "CLI-001", "--slice", "verify price table")
        packet = json.loads((homes[0] / "waves/001/packets/recurrence.json").read_text())
        recurrence = {**body, **{k: packet[k] for k in of.PACKET_IDENTITY_FIELDS}}
        notes = self.tmp / body["result_ref"]
        notes.write_text("CLI-001 price fixture failed")
        digest = hashlib.sha256(notes.read_bytes()).hexdigest()
        recurrence["residual"] = {
            **body["residual"], "evidence": f"CLI-001 failed in notes.md\nartifact_sha: {digest}",
        }
        self._plant(homes[0], "recurrence.json", recurrence)
        self._ok("learn", "--accept", check_id)
        red = subprocess.run([sys.executable, str(script)], cwd=str(self.tmp), capture_output=True, text=True, timeout=30)
        self.assertEqual(red.returncode, 1)
        self.assertIn("CLI-001", red.stderr)
        path = homes[0] / "waves/001/residuals/recurrence.json"
        history[path] = path.read_bytes()
        self._ok(*selected, "integrate", "--wave", "1")
        (self.tmp / "repair.log").write_text("fixture: price table displayed")
        self._ok(*selected, "spec", "--verified-contract", "CLI-001", "--takeover", "--cite", "repair.log")
        green = subprocess.run([sys.executable, str(script)], cwd=str(self.tmp), capture_output=True, text=True, timeout=30)
        self.assertEqual(green.returncode, 0, green.stderr)
        self._ok(*selected, "patch", "--done-when-closed")
        self._ok(*selected, "integrate", "--wave", "1", "--apply", "--recompute")
        ledger = json.loads((homes[0] / "REQUIREMENTS.json").read_bytes())
        self.assertEqual(ledger["requirements"][0]["status"], "verified_contract")
        self._ok(*selected, "phase", "cut", "--force", "--reason", "test the repaired price fixture")
        wave = path.parents[1]
        report = json.loads((wave / "report.json").read_bytes())
        self.assertNotEqual(report["integration"]["input_hash"], report["integration"]["previous_input_hash"])
        observations = json.loads((wave / "integrations/observations.json").read_bytes())
        self.assertEqual(observations["input_hash"], report["integration"]["input_hash"])
        green = subprocess.run([sys.executable, str(script)], cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(green.returncode, 0, green.stderr)
        self.assertEqual(history, {path: path.read_bytes() for path in history})

    def test_a_child_cannot_propose_or_accept(self) -> None:
        homes = self._fields()
        self._plant(homes[0], "a.json", residual("one"))
        self._plant(homes[1], "b.json", residual("two"))
        refused = run_of(self.tmp, "learn", "--checks", env={"OF_CHILD": "explorer"})
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("child-forge", refused.stderr)
        self.assertIn("--checks", refused.stderr)
        self.assertFalse((self.tmp / "scripts").exists())


if __name__ == "__main__":
    unittest.main()
