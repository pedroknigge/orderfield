#!/usr/bin/env python3
"""of init writes .orderfield/feature-map.md and derives done_when from its rows."""
from __future__ import annotations

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


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", "OF_NO_GC_AUTO": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    for key in ("OF_CHILD", "OF_FIELD", "OF_ADAPTER"):
        env.pop(key, None)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


class PlanFeatureMapInit(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-plan-feature-map-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / ".orderfield"

    def _ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = run_of(self.tmp, *args)
        self.assertEqual(proc.returncode, 0, f"{args}: {proc.stdout}{proc.stderr}")
        return proc

    def _order(self) -> dict:
        return json.loads((self.home / "ORDER.json").read_text(encoding="utf-8"))

    def _map(self) -> str:
        return (self.home / "feature-map.md").read_text(encoding="utf-8")

    def _price(self) -> None:
        (self.tmp / "price_cli.py").write_text(
            'from pathlib import Path\n'
            'Path("ran.txt").write_text("ran\\n")\n'
            'print("price table")\n',
            encoding="utf-8",
        )

    def _verified(self) -> None:
        self._ok("spec", "--add", "CLI-001", "--text", "the CLI prints a price table")
        (self.tmp / "surface.log").write_text("$ price\nprice table\n", encoding="utf-8")
        self._ok("spec", "--verified-contract", "CLI-001", "--cite", "surface.log")

    def test_init_writes_the_map_and_close_runs_that_command(self) -> None:
        self._price()
        init = self._ok(
            "init",
            "--mission",
            "show prices with `python3 price_cli.py`",
            "--phase",
            "explore",
        )
        self.assertIn("feature-map  .orderfield/feature-map.md", init.stdout)
        self.assertFalse((self.tmp / "ran.txt").exists())
        text = self._map()
        self.assertIn("| Feature | Reach | Proof |", text)
        self.assertIn("| price_cli.py | `python3 price_cli.py` | `python3 price_cli.py` |", text)
        self.assertEqual(self._order()["done_when"], ["`python3 price_cli.py`"])
        self._verified()
        closed = self._ok("close")
        self.assertIn("CLOSED", closed.stdout)
        self.assertTrue((self.tmp / "ran.txt").is_file())
        doc = json.loads((self.home / "CLOSE.json").read_text(encoding="utf-8"))
        row = doc["done_when"][0]
        self.assertEqual(row["command"], "python3 price_cli.py")
        self.assertEqual(row["exit"], 0)
        self.assertIn("price table", row["output"])

    def test_missing_program_is_named_and_close_stores_nothing(self) -> None:
        self._price()
        self._ok(
            "init",
            "--mission",
            "prices `python3 price_cli.py` and `node gone.js`",
            "--phase",
            "explore",
        )
        text = self._map()
        self.assertIn("| gone.js | `node gone.js` | cannot run: gone.js is missing |", text)
        self.assertNotIn("`cannot run:", text)
        self.assertEqual(
            self._order()["done_when"],
            ["`python3 price_cli.py`", "cannot run: gone.js is missing"],
        )
        self._verified()
        refused = run_of(self.tmp, "close")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("gone.js", refused.stderr)
        self.assertIn("cannot run:", refused.stderr)
        self.assertFalse((self.home / "CLOSE.json").is_file())

    def test_no_command_keeps_the_contrast_criterion(self) -> None:
        self._ok("init", "--mission", "pricing tool", "--phase", "explore")
        self.assertIn("cannot run: no command", self._map())
        self.assertNotIn("`", self._map().split("cannot run: no command", 1)[0].split("| Proof |", 1)[-1])
        self.assertEqual(
            self._order()["done_when"],
            ["of contrast RESOLVED then of close"],
        )

    def test_explicit_done_when_is_kept(self) -> None:
        kept = "`python3 -c 'print(9)'` kept"
        self._ok(
            "init",
            "--mission",
            "pricing tool",
            "--phase",
            "explore",
            "--done-when",
            kept,
        )
        self.assertIn("cannot run: no command", self._map())
        self.assertEqual(self._order()["done_when"], [kept])


if __name__ == "__main__":
    unittest.main()
