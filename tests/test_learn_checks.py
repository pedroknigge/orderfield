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
        red = subprocess.run([sys.executable, str(script)], cwd=str(self.tmp), capture_output=True, text=True, timeout=30)
        self.assertEqual(red.returncode, 1)
        self.assertIn("CLI-001", red.stderr)
        for home in homes:
            shutil.rmtree(home / "waves")
        green = subprocess.run([sys.executable, str(script)], cwd=str(self.tmp), capture_output=True, text=True, timeout=30)
        self.assertEqual(green.returncode, 0, green.stderr)

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
