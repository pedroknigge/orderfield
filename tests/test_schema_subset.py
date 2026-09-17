#!/usr/bin/env python3
"""Public schema subset: anyOf / maxLength are enforced, not claimed."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import of  # noqa: E402  — shipped kernel, not a copy

DONE = ROOT / "assets" / "fixtures" / "residual.done.json"


def _load_schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


class SchemaSubsetHonesty(unittest.TestCase):
    """C-030: runtime validate_schema matches the public-schema subset."""

    def test_public_schemas_use_only_implemented_keywords(self) -> None:
        unknown: list[str] = []
        for name in of.PUBLIC_SCHEMA_FILES:
            schema = _load_schema(name)
            unknown.extend(
                f"{name}{path[1:]}" if path.startswith("$") else f"{name}.{path}"
                for path in of.schema_unknown_keywords(schema)
            )
        self.assertEqual(unknown, [], unknown)

    def test_anyof_adapter_hints_requires_tier_or_model(self) -> None:
        schema = _load_schema("packet.schema.json")["properties"]["adapter_hints"]
        self.assertTrue(
            any("anyOf" in err for err in of.validate_schema({}, schema, "hints")),
            of.validate_schema({}, schema, "hints"),
        )
        self.assertEqual(of.validate_schema({"tier": "cheap"}, schema, "hints"), [])
        self.assertEqual(
            of.validate_schema({"model": "gpt-5-mini"}, schema, "hints"),
            [],
        )
        self.assertEqual(
            of.validate_schema(
                {"tier": "frontier", "model": "grok-4.6"}, schema, "hints"
            ),
            [],
        )

    def test_object_form_additional_properties_rejects_packed_pulse_verdict(
        self,
    ) -> None:
        schema = _load_schema("session.schema.json")["properties"]["pulse_verdicts"]
        self.assertEqual(
            of.validate_schema({"child": "ALIVE"}, schema, "pulse"), []
        )
        self.assertEqual(
            of.validate_schema({"child": "QUIET"}, schema, "pulse"), []
        )
        self.assertEqual(
            of.validate_schema({"child": "STALE"}, schema, "pulse"), []
        )
        toy = {"additionalProperties": {"enum": ["ALIVE", "QUIET", "STALE"]}}
        self.assertEqual(of.validate_schema({"child": "ALIVE"}, toy, "pulse"), [])
        errs = of.validate_schema({"child": "PACKED"}, schema, "pulse")
        self.assertTrue(any("must be one of" in err for err in errs), errs)
        self.assertTrue(any("ALIVE" in err for err in errs), errs)
        toy_errs = of.validate_schema({"child": "PACKED"}, toy, "pulse")
        self.assertTrue(any("must be one of" in err for err in toy_errs), toy_errs)

    def test_pattern_properties_validates_matching_keys(self) -> None:
        schema = {
            "type": "object",
            "patternProperties": {"^x_": {"type": "integer", "minimum": 1}},
        }
        self.assertEqual(of.validate_schema({"x_1": 2}, schema, "idx"), [])
        errs = of.validate_schema({"x_1": 0}, schema, "idx")
        self.assertTrue(any("must be >=" in err for err in errs), errs)

    def test_maxlength_denied_actions_item(self) -> None:
        schema = _load_schema("residual.schema.json")["properties"]["denied_actions"][
            "items"
        ]
        self.assertEqual(of.validate_schema("x" * 256, schema, "item"), [])
        errs = of.validate_schema("x" * 257, schema, "item")
        self.assertTrue(any("at most 256" in err for err in errs), errs)

    def test_validate_residual_refuses_overlong_denied_action(self) -> None:
        residual = json.loads(DONE.read_text(encoding="utf-8"))
        self.assertEqual(of.validate_residual(residual), [])
        residual["denied_actions"] = ["x" * 257]
        errs = of.validate_residual(residual)
        self.assertTrue(any("at most 256" in err for err in errs), errs)

    def test_validate_packet_refuses_empty_adapter_hints(self) -> None:
        packet = {
            "v": 1,
            "order_rev": 1,
            "order": {
                "id": "ord_deadbeef",
                "rev": 1,
                "mission": "schema subset",
                "phase": "explore",
                "done_when": ["tests name anyOf and maxLength"],
                "constraints": [],
                "workspace": {
                    "readable": ["."],
                    "writable_by_slaves": [".orderfield/work/scratch/"],
                    "forbidden": [".orderfield/ORDER.json"],
                },
                "thresholds": {
                    "tool_failures": 3,
                    "divergence": 0.5,
                    "local_budget_pct": 80,
                    "novelty": False,
                },
            },
            "slice": "prove anyOf",
            "role": "explorer",
            "residual_path": ".orderfield/work/residuals/x.json",
            "scratch_dir": ".orderfield/work/scratch/x/",
            "budget": {"tokens": 0, "seconds": 60},
            "adapter_hints": {},
        }
        errs = of.validate_packet(packet)
        self.assertTrue(
            any("anyOf" in err or "tier or model" in err for err in errs),
            errs,
        )


if __name__ == "__main__":
    unittest.main()
