#!/usr/bin/env python3
"""SCOPE-GODSPLIT is shipped: field.py re-exports public form names, not internals.

Named owners are of.wal / of.learn / of.retain. Remaining field.py is the
field I/O owner. A later line-count Holding is not an open god-split.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import of  # noqa: E402

_FIELD_SRC = Path(of.field.__file__).read_text(encoding="utf-8")


class FieldFormSplit(unittest.TestCase):
    def test_named_owners_are_not_reimplemented_in_field(self) -> None:
        for needle in (
            r"^class FieldWal\b",
            r"^class FieldLearnings\b",
            r"^class FieldRetain\b",
            r"^def dump_json\b",
            r"^def save_learning\b",
            r"^def plan_field_retention\b",
        ):
            self.assertIsNone(
                re.search(needle, _FIELD_SRC, re.M),
                f"field.py re-implements SCOPE-GODSPLIT owner {needle}",
            )

    def test_public_reexports_are_the_form_modules(self) -> None:
        self.assertIs(of.field.dump_json, of.wal.dump_json)
        self.assertIs(of.field.load_json, of.wal.load_json)
        self.assertIs(of.field.field_generation, of.wal.field_generation)
        self.assertIs(of.field.FieldWal, of.wal.FieldWal)
        self.assertIs(of.field.save_learning, of.learn.save_learning)
        self.assertIs(of.field.learning_accepted, of.learn.learning_accepted)
        self.assertIs(of.field.FieldLearnings, of.learn.FieldLearnings)
        self.assertIs(of.field.plan_field_retention, of.retain.plan_field_retention)
        self.assertIs(of.field.FieldRetain, of.retain.FieldRetain)
        self.assertIs(of.field.ClosedFieldArchive, of.retain.ClosedFieldArchive)

    def test_field_talks_to_form_classes(self) -> None:
        self.assertIn("status", of.field.FieldWal.VIEW_COMMANDS)
        self.assertIn("resume", of.field.FieldWal.VIEW_COMMANDS)
        self.assertTrue(hasattr(of.field.FieldWal, "read_current"))
        self.assertTrue(hasattr(of.field.FieldWal, "refuse_live_spec_tamper"))
        self.assertTrue(hasattr(of.field.FieldWal, "materialize_current"))
        self.assertTrue(hasattr(of.field.FieldLearnings, "format_continuation"))
        self.assertIs(of.field.FieldRetain.archive, of.retain.ClosedFieldArchive)

    def test_private_form_names_stay_on_owner_modules(self) -> None:
        for name in (
            "_WAL_VIEW_COMMANDS",
            "_wal_read_current",
            "_WalGeneration",
            "_refuse_live_spec_tamper",
            "_materialize_current_only",
            "_filter_learnings",
            "_safe_unlink",
        ):
            self.assertFalse(
                hasattr(of.field, name),
                f"of.field still re-exports private {name}",
            )
        self.assertTrue(hasattr(of.wal, "_WAL_VIEW_COMMANDS"))
        self.assertTrue(hasattr(of.learn, "_filter_learnings"))
        self.assertTrue(hasattr(of.retain, "_safe_unlink"))


if __name__ == "__main__":
    unittest.main()
