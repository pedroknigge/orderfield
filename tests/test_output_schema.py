#!/usr/bin/env python3
"""agy --json-schema reuses residual.codex. Claude omit. Not a new schema."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402

CODEX_RESIDUAL_SCHEMA = ROOT / "schemas" / "residual.codex.schema.json"


class OutputSchemaArgv(unittest.TestCase):
    """Reuse residual.codex.schema.json. Codex path stays. Claude omit."""

    def setUp(self) -> None:
        self._trust = os.environ.get("OF_TRUST")
        os.environ.pop("OF_TRUST", None)
        self.packet = {"child_id": "c1", "budget": {"seconds": 60}}
        self.residual = Path("/tmp/of-output-schema-residual.json")

    def tearDown(self) -> None:
        if self._trust is None:
            os.environ.pop("OF_TRUST", None)
        else:
            os.environ["OF_TRUST"] = self._trust

    def argv(self, adapter: str) -> list:
        return of.build_spawn_argv(
            adapter, "PROMPT", self.packet, self.residual, dry_run=True
        )

    def test_table_reuses_codex_file(self) -> None:
        self.assertEqual(of.OutputSchema.FILENAME, "residual.codex.schema.json")
        self.assertEqual(of.OutputSchema.path(), CODEX_RESIDUAL_SCHEMA)
        self.assertEqual(of.OutputSchema.flag("codex"), "--output-schema")
        self.assertEqual(of.OutputSchema.flag("agy"), "--json-schema")
        self.assertIsNone(of.OutputSchema.flag("claude"))
        self.assertIn("claude", of.OutputSchema.OMIT)
        self.assertIn("inline", of.OutputSchema.OMIT["claude"])
        self.assertIn("qwen", of.OutputSchema.OMIT)

    def test_codex_still_uses_output_schema_and_dash_o(self) -> None:
        argv = self.argv("codex")
        self.assertIn("-o", argv)
        self.assertEqual(argv[argv.index("-o") + 1], str(self.residual))
        self.assertIn("--output-schema", argv)
        schema_path = Path(argv[argv.index("--output-schema") + 1])
        self.assertEqual(schema_path, CODEX_RESIDUAL_SCHEMA)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["usage"]["type"], ["object", "null"])
        self.assertNotIn("--json-schema", argv)

    def test_agy_json_schema_is_same_file_before_dash_p(self) -> None:
        argv = self.argv("agy")
        self.assertIn("--json-schema", argv)
        self.assertEqual(
            Path(argv[argv.index("--json-schema") + 1]),
            CODEX_RESIDUAL_SCHEMA,
        )
        self.assertNotIn("--output-schema", argv)
        self.assertLess(argv.index("--json-schema"), argv.index("-p"))
        self.assertEqual(argv[argv.index("-p") + 1], "PROMPT")
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")

    def test_claude_omits_schema_flag_and_keeps_stream_json(self) -> None:
        argv = self.argv("claude")
        self.assertNotIn("--json-schema", argv)
        self.assertNotIn("--output-schema", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")

    def test_unsupported_adapters_omit(self) -> None:
        for adapter in ("qwen", "cursor", "opencode", "orca", "grok"):
            with self.subTest(adapter=adapter):
                argv = self.argv(adapter)
                self.assertNotIn("--json-schema", argv)
                self.assertNotIn("--output-schema", argv)


class OutputSchemaExtract(unittest.TestCase):
    """structured_output is the agy residual slot. Reuse StreamJson.residual."""

    def test_residual_from_structured_output(self) -> None:
        body = {
            "status": "done",
            "residual": {
                "wants_to_change": [],
                "evidence": "ok",
                "proposed_patch": None,
            },
            "metrics": {
                "uncertainty": 0.1,
                "divergence": 0.0,
                "tool_failures": 0,
                "novelty": False,
            },
            "result_ref": ".orderfield/work/scratch/c1/notes.md",
        }
        envelope = {
            "conversation_id": "agy-1",
            "status": "SUCCESS",
            "structured_output": body,
        }
        self.assertEqual(of.StreamJson.residual(envelope), body)
        wrapped = of.StreamJson.residual(
            {"type": "result", "structured_output": json.dumps(body)}
        )
        self.assertEqual(wrapped, body)


class OutputSchemaRedact(unittest.TestCase):
    def test_long_json_schema_path_keeps_basename(self) -> None:
        deep = (
            "/Users/pedro/.gemini/antigravity-cli/skills/"
            + ("orderfield-" + "x" * 40)
            + "/schemas/residual.codex.schema.json"
        )
        self.assertGreater(len(deep), of.ArgvRedact.PROMPT_CHARS)
        preview = of.argv_preview(["agy", "--json-schema", deep, "-p", "PROMPT"])
        self.assertIn("residual.codex.schema.json", preview)
        self.assertIn("--json-schema", preview)
        self.assertNotIn("<prompt>", preview.split("--json-schema", 1)[1].split()[0])
        self.assertNotIn(deep, preview)
        eq_preview = of.argv_preview(["agy", f"--json-schema={deep}", "short"])
        self.assertIn("residual.codex.schema.json", eq_preview)
        self.assertIn("short", eq_preview)


class OutputSchemaSkill(unittest.TestCase):
    """Skill drives the cut: agy --json-schema; Claude omit."""

    def test_skill_and_alias_teach_agy_json_schema_and_claude_omit(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        folded = table.casefold()
        self.assertIn("--json-schema", folded)
        self.assertIn("agy", folded)
        self.assertIn("omit", folded)
        self.assertIn("claude", folded)
        self.assertIn("residual.codex", folded)
        skill_fold = skill.casefold()
        self.assertIn("--json-schema", skill_fold)
        self.assertIn("inline", skill_fold)
        self.assertIn("stream-json", skill_fold)
        alias_fold = alias.casefold()
        self.assertIn("--json-schema", alias_fold)
        self.assertIn("agy", alias_fold)
        self.assertIn("omit", alias_fold)
        self.assertIn("claude", alias_fold)


if __name__ == "__main__":
    unittest.main()
