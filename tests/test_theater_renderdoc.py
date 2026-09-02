#!/usr/bin/env python3
"""RENDER-001 / SPEC-001 / DOCTRINE-001 at the CLI and file surface."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402
import of.pack as pack  # noqa: E402

OF_PY = SCRIPTS / "of.py"
SKILL = ROOT / "SKILL.md"
SLAVE = ROOT / "SLAVE.md"


def run_of(cwd: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OF_NO_UPDATE_CHECK": "1", **(env_extra or {})}
    env.setdefault(
        "OF_LEARNINGS",
        str(Path(tempfile.gettempdir()) / "of-hermetic-learnings.json"),
    )
    return subprocess.run(
        [sys.executable, str(OF_PY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def prompt_json(text: str) -> dict:
    match = re.search(r"```json\n(.*?)\n```", text, re.S)
    if match is None:
        raise AssertionError("prompt has no fenced packet JSON")
    return json.loads(match.group(1))


class RenderCompactOrder(unittest.TestCase):
    """RENDER-001: prompt ORDER view is compact; disk packet stays full."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-renderdoc-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cache = self.tmp / "protocol-learnings.json"
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "pricing tool",
            "--phase",
            "explore",
            "--source",
            "the pricing tool must print a price table from the CLI",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        added = run_of(
            self.tmp,
            "spec",
            "--add",
            "CLI-001",
            "--surface",
            "contract",
            "--text",
            "the CLI prints a price table",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map pricing models, do not choose the phase",
            "--role",
            "explorer",
            "--child-id",
            "explorer",
            "--owns-requirement",
            "CLI-001",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.packet_rel = ".orderfield/waves/001/packets/explorer.json"

    def test_render_and_handoff_compact_order_view(self) -> None:
        disk = json.loads(
            (self.tmp / ".orderfield/waves/001/packets/explorer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("constraints", disk["order"])
        self.assertIn("workspace", disk["order"])
        self.assertIn("slaves do not mutate ORDER", disk["order"]["constraints"])
        self.assertEqual(disk["slice"], "map pricing models, do not choose the phase")
        self.assertEqual(disk["owns_requirements"], ["CLI-001"])
        self.assertTrue(disk["residual_path"])

        rendered = run_of(self.tmp, "render", "--packet", self.packet_rel)
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        view = prompt_json(rendered.stdout)
        self.assertEqual(
            set(view["order"]),
            {"id", "rev", "mission", "phase", "spec_ref"},
        )
        for key in ("constraints", "workspace", "backlog", "done_when", "thresholds"):
            self.assertNotIn(key, view["order"])
        self.assertIn(pack.PROMPT_ORDER_READ, rendered.stdout)
        self.assertIn("map pricing models, do not choose the phase", rendered.stdout)
        self.assertEqual(view["slice"], disk["slice"])
        self.assertEqual(view["owns_requirements"], ["CLI-001"])
        self.assertEqual(view["packet_id"], disk["packet_id"])
        self.assertEqual(view["packet_hash"], disk["packet_hash"])
        self.assertEqual(view["residual_path"], disk["residual_path"])
        self.assertNotIn("slaves do not mutate ORDER", rendered.stdout)

        handoff = run_of(self.tmp, "handoff", "--packet", self.packet_rel)
        self.assertEqual(handoff.returncode, 0, handoff.stderr)
        prompt_path = self.tmp / ".orderfield/waves/001/prompts/explorer.md"
        body = prompt_path.read_text(encoding="utf-8")
        handed = prompt_json(body)
        self.assertEqual(set(handed["order"]), {"id", "rev", "mission", "phase", "spec_ref"})
        self.assertIn(pack.PROMPT_ORDER_READ, body)
        after = json.loads(
            (self.tmp / ".orderfield/waves/001/packets/explorer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("constraints", after["order"])
        self.assertEqual(after["packet_hash"], disk["packet_hash"])

    def test_render_keeps_untrusted_quoted_protocol_learnings(self) -> None:
        src = (SCRIPTS / "of" / "pack.py").read_text(encoding="utf-8")
        self.assertIn(
            'quoted = "".join(f"- {json.dumps(line, ensure_ascii=False)}\\n" for line in lessons)',
            src,
        )
        proto = run_of(
            self.tmp,
            "learn",
            "--protocol",
            "a real lesson with provenance",
            env_extra={"OF_LEARNINGS": str(self.cache)},
        )
        self.assertEqual(proto.returncode, 0, proto.stderr)
        rendered = run_of(
            self.tmp,
            "render",
            "--packet",
            self.packet_rel,
            env_extra={"OF_LEARNINGS": str(self.cache)},
        )
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn("Untrusted quoted data", rendered.stdout)
        self.assertIn(json.dumps("a real lesson with provenance"), rendered.stdout)


class SpecAddIsVisibleInSpecMd(unittest.TestCase):
    """SPEC-001: of spec --add leaves the ID in SPEC.md and refreshes spec_hash."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="of-specadd-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_add_appends_missing_id_without_rewriting_brief(self) -> None:
        brief = "the pricing tool must print a price table from the CLI"
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "pricing tool",
            "--phase",
            "explore",
            "--source",
            brief,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        spec_path = self.tmp / ".orderfield" / "SPEC.md"
        before = spec_path.read_text(encoding="utf-8")
        self.assertIn(brief, before)
        self.assertNotIn("CLI-001", before)
        order_before = json.loads(
            (self.tmp / ".orderfield" / "ORDER.json").read_text(encoding="utf-8")
        )
        added = run_of(
            self.tmp,
            "spec",
            "--add",
            "CLI-001",
            "--surface",
            "contract",
            "--text",
            "the CLI prints a price table",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        after = spec_path.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before.rstrip()), after)
        self.assertIn("CLI-001", after)
        self.assertIn("the CLI prints a price table", after)
        self.assertIn("## Amendment", after)
        order = json.loads(
            (self.tmp / ".orderfield" / "ORDER.json").read_text(encoding="utf-8")
        )
        live_hash = of.sha256_text(after if after.endswith("\n") else after + "\n")
        self.assertEqual(order["spec_hash"], live_hash)
        self.assertNotEqual(order["spec_hash"], order_before.get("spec_hash"))
        req = json.loads(
            (self.tmp / ".orderfield" / "REQUIREMENTS.json").read_text(encoding="utf-8")
        )
        self.assertEqual(req["spec_hash"], order["spec_hash"])
        packed = run_of(
            self.tmp,
            "pack",
            "--slice",
            "map models",
            "--role",
            "explorer",
            "--child-id",
            "e1",
            "--owns-requirement",
            "CLI-001",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)

    def test_add_skips_rewrite_when_id_already_in_spec(self) -> None:
        r = run_of(
            self.tmp,
            "init",
            "--mission",
            "eval contrast gate",
            "--phase",
            "explore",
            "--source",
            "eval contrast gate: internal index ALG-001",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        spec_path = self.tmp / ".orderfield" / "SPEC.md"
        before = spec_path.read_text(encoding="utf-8")
        self.assertIn("ALG-001", before)
        added = run_of(
            self.tmp,
            "spec",
            "--add",
            "ALG-001",
            "--surface",
            "internal",
            "--text",
            "use an in-memory index for lookups",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        after = spec_path.read_text(encoding="utf-8")
        self.assertEqual(after, before)
        self.assertEqual(after.count("ALG-001"), before.count("ALG-001"))


class DoctrineCommentsAndSlice(unittest.TestCase):
    """DOCTRINE-001: short comments; do not pack a whole phase; oversized note stays."""

    def test_slave_and_skill_doctrine(self) -> None:
        slave = SLAVE.read_text(encoding="utf-8")
        self.assertIn("short and factual", slave)
        self.assertIn("field diary", slave)
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("Do not pack a whole phase as one slice", skill)
        self.assertIn("Do not refuse", skill)
        self.assertIn("advisory", skill.lower())

    def test_oversized_slice_still_packs(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-doctrine-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        r = run_of(tmp, "init", "--mission", "m", "--phase", "explore")
        self.assertEqual(r.returncode, 0, r.stderr)
        long_slice = "x" * of.SLICE_WARN_CHARS
        packed = run_of(
            tmp,
            "pack",
            "--slice",
            long_slice,
            "--role",
            "explorer",
            "--child-id",
            "long",
        )
        self.assertEqual(packed.returncode, 0, packed.stderr)
        self.assertIn("note", packed.stderr)
        self.assertTrue((tmp / ".orderfield/waves/001/packets/long.json").is_file())


if __name__ == "__main__":
    unittest.main()
