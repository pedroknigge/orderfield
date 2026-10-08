#!/usr/bin/env python3
"""Read verbs are total over field content (FUZZFIX).

A torn, non-UTF-8 or wrong-typed field file outside the WAL (a child's
residual or scope file, the ACTIVE pointer, a live cache copy) never makes
`of resume`, `of resume --json` or `of status` exit nonzero: they report
(REPAIR / RESTORE). Only a broken WAL head refuses (wal-broken, W1).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import run_of  # noqa: E402

WAVE = ".orderfield/waves/001"
TARGETS = (
    ".orderfield/ACTIVE",
    ".orderfield/ORDER.json",
    ".orderfield/state.json",
    ".orderfield/session.json",
    f"{WAVE}/report.json",
    f"{WAVE}/residuals/c1.json",
    f"{WAVE}/scope/c1.json",
    ".orderfield/wal/MATERIALIZED.json",
)
DAMAGE = {
    "non-utf8": lambda b: b"\xff\xfe\x00junk",
    "torn": lambda b: b[: max(1, len(b) // 2)],
    "array": lambda b: b"[]\n",
}


class ReadPathTotal(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = Path(tempfile.mkdtemp(prefix="of-readtotal-"))
        cls.tpl = cls.base / "tpl"
        cls.tpl.mkdir()
        for args in (
            ("init", "--mission", "m", "--phase", "explore", "--source", "read paths are total"),
            ("pack", "--slice", "read the tree", "--role", "explorer", "--child-id", "c1"),
        ):
            assert run_of(cls.tpl, *args).returncode == 0, args
        tpl = json.loads((cls.tpl / WAVE / "prompts/c1.RESIDUAL.template.json").read_text())
        tpl.update({"status": "blocked", "result_ref": ""})
        tpl["residual"]["evidence"] = "blocked: nothing to read"
        (cls.tpl / WAVE / "residuals").mkdir(exist_ok=True)
        (cls.tpl / WAVE / "residuals/c1.json").write_text(json.dumps(tpl, indent=2))
        for args in (("collect",), ("integrate", "--apply")):
            assert run_of(cls.tpl, *args).returncode == 0, args

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_damaged_field_file_never_fails_a_read_verb(self) -> None:
        n = 0
        for rel in TARGETS:
            for kind, damage in DAMAGE.items():
                n += 1
                root = self.base / f"case{n}"
                shutil.copytree(self.tpl, root, symlinks=True)
                path = root / rel
                self.assertTrue(path.is_file(), rel)
                path.write_bytes(damage(path.read_bytes()))
                for args in (("resume", "--json"), ("resume",), ("status",)):
                    with self.subTest(rel=rel, kind=kind, cmd=args):
                        r = run_of(root, *args)
                        self.assertNotIn("Traceback", r.stderr)
                        self.assertEqual(r.returncode, 0, r.stderr[-400:])
                shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
