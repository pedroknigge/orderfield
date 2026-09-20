#!/usr/bin/env python3
"""HostRam suggest-band + once-per-field agent-band consent. #281."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402

OF_PY = SCRIPTS / "of.py"
LINUX_16G = "MemTotal:       16777216 kB\nMemAvailable:    2097152 kB\n"
LINUX_8G = "MemTotal:        8388608 kB\nMemAvailable:     512000 kB\n"
LINUX_32G = "MemTotal:       33554432 kB\nMemAvailable:    4194304 kB\n"
MAC_16G = "17179869184\n"
MAC_8G = "8589934592\n"
WIN_64G = 64 * 1024**3
WIN_AVAIL = 8 * 1024**3


def run_of(
    cwd: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class HostRamSuggestBand(unittest.TestCase):
    """Pure GB → band table. Not a spawn cap."""

    def test_table(self) -> None:
        cases = (
            (0, "1-4"),
            (8, "1-4"),
            (8.0, "1-4"),
            (8.1, "5-10"),
            (16, "5-10"),
            (23.9, "5-10"),
            (24, "10-50"),
            (32, "10-50"),
            (64, "10-50"),
            (128, "10-50"),
        )
        for gb, band in cases:
            with self.subTest(gb=gb):
                self.assertEqual(of.HostRam.suggest_band(gb), band)
        self.assertIsNone(of.HostRam.suggest_band(None))
        self.assertIsNone(of.HostRam.suggest_band(-1))

    def test_linux_meminfo_fixture(self) -> None:
        total, avail = of.HostRam.parse_linux_meminfo(LINUX_16G)
        self.assertEqual(total, 16777216 * 1024)
        self.assertEqual(avail, 2097152 * 1024)
        doc = of.HostRam.measure(system="Linux", meminfo_text=LINUX_16G)
        self.assertEqual(doc["ram_total_gb"], 16.0)
        self.assertEqual(doc["ram_avail_gb"], 2.0)
        self.assertEqual(doc["suggested_band"], "5-10")
        eight = of.HostRam.measure(system="Linux", meminfo_text=LINUX_8G)
        self.assertEqual(eight["suggested_band"], "1-4")
        big = of.HostRam.measure(system="Linux", meminfo_text=LINUX_32G)
        self.assertEqual(big["suggested_band"], "10-50")

    def test_macos_memsize_fixture(self) -> None:
        self.assertEqual(of.HostRam.parse_macos_memsize(MAC_16G), 16 * 1024**3)
        self.assertEqual(
            of.HostRam.measure(system="Darwin", memsize_text=MAC_8G)["suggested_band"],
            "1-4",
        )
        self.assertEqual(
            of.HostRam.measure(system="Darwin", memsize_text=MAC_16G)["suggested_band"],
            "5-10",
        )

    def test_windows_status_fixture(self) -> None:
        total, avail = of.HostRam.parse_windows_status(WIN_64G, WIN_AVAIL)
        self.assertEqual(total, WIN_64G)
        self.assertEqual(avail, WIN_AVAIL)
        doc = of.HostRam.measure(
            system="Windows", win_total=WIN_64G, win_avail=WIN_AVAIL
        )
        self.assertEqual(doc["ram_total_gb"], 64.0)
        self.assertEqual(doc["suggested_band"], "10-50")

    def test_low_avail_is_note_not_refuse(self) -> None:
        doc = of.HostRam.measure(system="Linux", meminfo_text=LINUX_8G)
        note = of.HostRam.low_avail_note(doc)
        self.assertIsNotNone(note)
        self.assertIn("not a spawn refuse", note or "")
        lines = of.HostRam.doctor_lines(doc)
        joined = "\n".join(lines)
        self.assertIn("ram_total_gb", joined)
        self.assertIn("suggested=1-4", joined)
        self.assertIn("not a spawn cap", joined)
        self.assertIn("cloud/remote", joined)

    def test_unknown_omits_invented_gb(self) -> None:
        doc = of.HostRam.measure(system="Plan9")
        self.assertIsNone(doc["ram_total_gb"])
        self.assertIsNone(doc["suggested_band"])
        self.assertEqual(of.HostRam.event_fields(doc), {})


class AgentBandUnit(unittest.TestCase):
    def test_normalize_en_dash_and_refuse_off(self) -> None:
        self.assertEqual(of.AgentBand.normalize_band("1–4"), "1-4")
        self.assertEqual(of.AgentBand.normalize_band("10—50"), "10-50")
        with patch("sys.stderr", new=StringIO()):
            with self.assertRaises(SystemExit):
                of.AgentBand.normalize_band("always-50")
            with self.assertRaises(SystemExit):
                of.AgentBand.normalize_band("off")

    def test_apply_stores_once_fields(self) -> None:
        order: dict = {}
        self.assertTrue(of.AgentBand.apply(order, band="5-10", multi_model="yes"))
        self.assertEqual(order["agent_band"], {"band": "5-10", "multi_model": True})
        self.assertFalse(of.AgentBand.apply(order, band="5-10", multi_model="yes"))
        self.assertTrue(of.AgentBand.apply(order, multi_model="no"))
        self.assertEqual(order["agent_band"]["multi_model"], False)

    def test_pack_note_is_advisory_not_cap(self) -> None:
        order = {"agent_band": {"band": "1-4", "multi_model": False}}
        note = of.AgentBand.pack_note(order, 5)
        self.assertIsNotNone(note)
        self.assertIn("1-4", note or "")
        self.assertIn("not a spawn cap", note or "")
        self.assertIn("do not treat as refuse", note or "")
        self.assertIsNone(of.AgentBand.pack_note({}, 50))

    def test_stamp_effort_defaults_medium(self) -> None:
        self.assertEqual(
            of.AgentBand.stamp_effort({"tier": "frontier"}),
            {"tier": "frontier", "effort": "medium"},
        )
        self.assertEqual(
            of.AgentBand.stamp_effort({"tier": "cheap", "effort": "low"}),
            {"tier": "cheap", "effort": "low"},
        )
        self.assertIsNone(of.AgentBand.stamp_effort(None))


class AgentBandCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-agent-band-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_init_stores_band_and_prints_ram_suggest(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "band consent",
            "--agent-band",
            "5-10",
            "--multi-model",
            "yes",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(order["agent_band"], {"band": "5-10", "multi_model": True})
        self.assertIn("ram_total_gb", r.stdout)
        self.assertIn("suggested=", r.stdout)
        self.assertIn("not a spawn cap", r.stdout)
        self.assertIn("cloud/remote", r.stdout)
        self.assertIn("agent_band  5-10 multi-model=yes", r.stdout)
        self.assertNotIn("always 50", r.stdout)

    def test_patch_stores_without_reinit(self) -> None:
        r = run_of(self.tmp, "init", "--mission", "later band")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertNotIn("agent_band", order)
        r = run_of(
            self.tmp, "patch", "--agent-band", "1-4", "--multi-model", "no"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        order = load_json(self.tmp / ".orderfield" / "ORDER.json")
        self.assertEqual(order["agent_band"], {"band": "1-4", "multi_model": False})
        self.assertIn("agent_band", r.stdout)

    def test_pack_note_changes_with_stored_band_and_medium_default(self) -> None:
        run_of(
            self.tmp,
            "init",
            "--mission",
            "hints",
            "--agent-band",
            "1-4",
            "--multi-model",
            "no",
        )
        run_of(self.tmp, "patch", "--model-hints", "field")
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "implement the owned files",
            "--role",
            "implementer",
            "--child-id",
            "impl1",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.assertIn("agent_band=1-4", packed.stdout)
        self.assertIn("not a spawn cap", packed.stdout)
        self.assertIn("multi-model no", packed.stdout)
        packet = load_json(
            self.tmp
            / ".orderfield"
            / "waves"
            / "001"
            / "packets"
            / "impl1.json"
        )
        self.assertEqual(packet["adapter_hints"].get("effort"), "medium")
        run_of(self.tmp, "unpack", "--child-id", "impl1", "--force")
        run_of(self.tmp, "patch", "--agent-band", "10-50")
        packed2 = run_of(
            self.tmp,
            "pack",
            "--slice",
            "implement the owned files again",
            "--role",
            "implementer",
            "--child-id",
            "impl2",
        )
        self.assertEqual(packed2.returncode, 0, packed2.stderr)
        self.assertIn("agent_band=10-50", packed2.stdout)
        self.assertNotIn("re-ask", packed2.stdout.casefold())

    def test_does_not_hard_cap_spawn_from_band(self) -> None:
        run_of(self.tmp, "init", "--mission", "no cap", "--agent-band", "1-4")
        # kernel cap is still max_children=4; packing 4 is allowed even on 1-4.
        for i in range(1, 5):
            r = run_of(
                self.tmp,
                "pack",
                "--slice",
                f"slice files part {i}",
                "--role",
                "explorer",
                "--child-id",
                f"e{i}",
            )
            self.assertEqual(r.returncode, 0, r.stderr)
        fifth = run_of(
            self.tmp,
            "pack",
            "--slice",
            "one more explorer slice",
            "--role",
            "explorer",
            "--child-id",
            "e5",
        )
        self.assertNotEqual(fifth.returncode, 0)
        self.assertIn("max_children", fifth.stderr)
        self.assertNotIn("agent_band", fifth.stderr)

    def test_doctor_exposes_ram_total_gb(self) -> None:
        run_of(self.tmp, "init", "--mission", "doctor ram", "--agent-band", "5-10")
        r = run_of(self.tmp, "doctor")
        self.assertIn(r.returncode, (0, 2), r.stderr)
        self.assertIn("ram_total_gb", r.stdout)
        self.assertIn("suggested=", r.stdout)
        self.assertIn("not a spawn cap", r.stdout)
        self.assertIn("cloud/remote", r.stdout)
        self.assertIn("agent_band   5-10", r.stdout)
        self.assertIn("do not re-ask", r.stdout)

    def test_status_prints_stored_band(self) -> None:
        run_of(
            self.tmp,
            "init",
            "--mission",
            "status band",
            "--agent-band",
            "10-50",
            "--multi-model",
            "yes",
        )
        r = run_of(self.tmp, "status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("agent_band  10-50 multi-model=yes", r.stdout)
        js = run_of(self.tmp, "status", "--json")
        self.assertEqual(js.returncode, 0, js.stderr)
        doc = json.loads(js.stdout.strip().splitlines()[0])
        self.assertEqual(doc["agent_band"]["band"], "10-50")
        self.assertTrue(doc["agent_band"]["multi_model"])


class SkillAgentBand(unittest.TestCase):
    """Stored band changes teaching; medium default; no per-wave re-ask."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_skill_alias_appendix_teach_once_medium_no_recap(self) -> None:
        from skill_surface import SkillSurface

        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("agent-band", table)
        self.assertIn("1-4", table)
        self.assertIn("5-10", table)
        self.assertIn("10-50", table)
        self.assertIn("multi-model", table)
        self.assertIn("medium", table)
        self.assertIn("do not re-ask", table)
        self.assertIn("of patch --agent-band", table)
        self.assertIn("must ask", table)
        self.assertNotIn("hard-cap", table)
        self.assertNotIn("always 50", table)
        for rel, text in (
            ("SKILL.md", core),
            ("of/SKILL.md", alias),
            ("references/skill-appendix.md", appendix),
        ):
            fold = text.casefold()
            with self.subTest(rel=rel):
                self.assertIn("agent-band", fold, rel)
                self.assertIn("medium", fold, rel)
                self.assertIn("do not re-ask", fold, rel)
                self.assertIn("not a spawn cap", fold, rel)
                self.assertIn("cloud", fold, rel)
                self.assertNotIn("always 50", fold, rel)
                self.assertNotIn("ask again each wave", fold, rel)
        self.assertLessEqual(
            SkillSurface.core_bytes(ROOT), SkillSurface.CORE_MAX_BYTES
        )


if __name__ == "__main__":
    unittest.main()
