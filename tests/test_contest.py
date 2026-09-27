#!/usr/bin/env python3
"""Contest — competing plans as sibling fields, selection by contrast.

contend opens N candidates sharing one brief; crown ranks them with
of-contrast evidence and crowns only a strict, above-floor winner.
Ties and below-floor fields exit 2 for a human. Losers are archived
with a CONTEST.json trail, never deleted.
"""
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
OF_PY = SCRIPTS / "of.py"

BRIEF = (
    "# Demo contest brief\n"
    "## Rules:\n"
    "- The tool must exit zero on a clean tree.\n"
)


def run_of(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault("OF_LEARNINGS", str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"))
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd), capture_output=True, text=True, env=env,
    )


def contest_of(stdout: str) -> dict[str, object]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"no JSON object in stdout:\n{stdout}")


def field_homes(cwd: Path) -> dict[str, Path]:
    base = cwd / ".orderfield" / "fields"
    out: dict[str, Path] = {}
    if base.is_dir():
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / "ORDER.json").is_file():
                out[child.name] = child
    return out


def read_order(home: Path) -> dict[str, object]:
    return json.loads((home / "ORDER.json").read_text(encoding="utf-8"))


def active_id(cwd: Path) -> str:
    return (cwd / ".orderfield" / "ACTIVE").read_text(encoding="utf-8").strip()


def stamp_verified(home: Path) -> str:
    """Simulate landed contract verification on every binding requirement."""
    req_path = home / "REQUIREMENTS.json"
    data = json.loads(req_path.read_text(encoding="utf-8"))
    reqs = [r for r in (data.get("requirements") or []) if isinstance(r, dict)]
    assert reqs, "contest brief must extract at least one requirement"
    for req in reqs:
        req["status"] = "verified_contract"
        req["owned_by"] = ["simulated-landing"]
    req_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return str(reqs[0].get("id"))


class ContendOpensSiblings(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-contest-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "contest demo", "--source", BRIEF)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_contend_opens_two_candidates_sharing_the_brief(self) -> None:
        r = run_of(self.tmp, "contend", "--candidates", "2", "--json")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        payload = contest_of(r.stdout)
        contest = str(payload["contest"])
        ids = [str(x) for x in payload["candidates"]]
        self.assertEqual(len(ids), 2)
        homes = field_homes(self.tmp)
        # parent promoted to fields/<id> plus the two candidates
        self.assertEqual(len(homes), 3)
        hashes = set()
        for fid in ids:
            order = read_order(homes[fid])
            block = order.get("contest")
            self.assertIsInstance(block, dict)
            assert isinstance(block, dict)
            self.assertEqual(block["id"], contest)
            self.assertEqual(block["candidates"], 2)
            self.assertEqual(block["max_gaps"], 0)
            hashes.add(str(block["spec_hash"]))
        parent_hash = json.loads(
            (self.tmp / ".orderfield" / "fields" / active_parent(self.tmp, ids)
             / "REQUIREMENTS.json").read_text(encoding="utf-8")
        )["spec_hash"]
        self.assertEqual(hashes, {str(parent_hash)})

    def test_contend_rejects_out_of_range_counts(self) -> None:
        for bad in ("1", "9"):
            r = run_of(self.tmp, "contend", "--candidates", bad)
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn("Traceback", r.stderr)


def active_parent(cwd: Path, ids: list[str]) -> str:
    homes = field_homes(cwd)
    others = [fid for fid in homes if fid not in ids]
    assert len(others) == 1
    return others[0]


class CrownSelectsByContrast(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-crown-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = run_of(self.tmp, "init", "--mission", "contest demo", "--source", BRIEF)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_of(self.tmp, "contend", "--candidates", "2", "--json")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        payload = contest_of(r.stdout)
        self.contest = str(payload["contest"])
        self.ids = [str(x) for x in payload["candidates"]]

    def test_below_floor_exits_2_and_changes_nothing(self) -> None:
        before = active_id(self.tmp)
        before_homes = sorted(field_homes(self.tmp))
        r = run_of(self.tmp, "crown", "--contest", self.contest)
        self.assertEqual(r.returncode, 2, r.stderr + r.stdout)
        self.assertIn("below_floor", r.stdout)
        self.assertEqual(active_id(self.tmp), before)
        self.assertEqual(sorted(field_homes(self.tmp)), before_homes)

    def test_tie_exits_2_with_floor_override(self) -> None:
        r = run_of(
            self.tmp, "crown", "--contest", self.contest, "--max-gaps", "5"
        )
        self.assertEqual(r.returncode, 2, r.stderr + r.stdout)
        self.assertIn("tie", r.stdout)

    def test_winner_is_crowned_and_losers_archived(self) -> None:
        winner, loser = self.ids
        stamp_verified(field_homes(self.tmp)[winner])
        r = run_of(self.tmp, "crown", "--contest", self.contest, "--json")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        result = contest_of(r.stdout)
        self.assertEqual(result["winner"], winner)
        self.assertEqual(result["outcome"], "winner-auto")
        self.assertEqual(active_id(self.tmp), winner)
        homes = field_homes(self.tmp)
        self.assertNotIn(loser, homes)
        archived = self.tmp / ".orderfield" / "archive" / loser
        self.assertTrue((archived / "CONTEST.json").is_file())
        trail = json.loads((archived / "CONTEST.json").read_text(encoding="utf-8"))
        self.assertEqual(trail["winner"], winner)
        order = read_order(homes[winner])
        block = order.get("contest")
        assert isinstance(block, dict)
        result_block = block.get("result")
        assert isinstance(result_block, dict)
        self.assertEqual(result_block["winner"], winner)

    def test_explicit_winner_crowns_on_tie(self) -> None:
        pick = self.ids[1]
        r = run_of(
            self.tmp,
            "crown",
            "--contest",
            self.contest,
            "--max-gaps",
            "5",
            "--winner",
            pick,
            "--reason",
            "human pick",
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("winner-human", r.stdout)
        self.assertEqual(active_id(self.tmp), pick)

    def test_unknown_contest_dies(self) -> None:
        r = run_of(self.tmp, "crown", "--contest", "ctg_deadbeef")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
