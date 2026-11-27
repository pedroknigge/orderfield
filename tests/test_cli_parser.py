#!/usr/bin/env python3
"""No flag abbreviation: a prefix is never silently widened into a real flag.

`--constraint` used to prefix-match `--constraints-add`; every parser in the
tree must refuse a flag that is not spelled in full.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from of.cli import build_parser  # noqa: E402

OF_PY = SCRIPTS / "of.py"


def parsers(parser: argparse.ArgumentParser) -> list[argparse.ArgumentParser]:
    out = [parser]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                out.extend(parsers(child))
    return out


def parse_rc(argv: list[str]) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            build_parser().parse_args(argv)
        except SystemExit as exc:
            return int(exc.code or 0), err.getvalue()
    return 0, err.getvalue()


class NoAbbrev(unittest.TestCase):
    def test_import_preserves_argparse_and_build_registers_list_options(self) -> None:
        code = (
            "import argparse\noriginal = argparse.ArgumentParser.parse_args\n"
            "import of.cli\nassert argparse.ArgumentParser.parse_args is original"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=SCRIPTS,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        parser = build_parser()
        for command in (["learn", "--list"], ["worktree", "list"]):
            self.assertTrue(parser.parse_args([*command, "--all"]).list_all)
            self.assertEqual(parser.parse_args([*command, "--cursor", "next"]).list_cursor, "next")
            self.assertEqual(parse_rc([*command, "--all", "--cursor", "next"])[0], 2)

    def test_every_parser_refuses_abbreviation(self) -> None:
        tree = parsers(build_parser())
        self.assertGreater(len(tree), 30)
        loose = [p.prog for p in tree if p.allow_abbrev]
        self.assertEqual(loose, [])

    def test_prefix_of_patch_flag_is_refused(self) -> None:
        rc, err = parse_rc(["patch", "--constraint", "x"])
        self.assertEqual(rc, 2)
        self.assertIn("--constraint", err)

    def test_full_flag_still_parses(self) -> None:
        ns = build_parser().parse_args(["patch", "--constraints-add", "x"])
        self.assertEqual(ns.cmd, "patch")

    def test_prefix_of_top_level_flag_is_refused(self) -> None:
        rc, _ = parse_rc(["--js", "status"])
        self.assertEqual(rc, 2)

    def test_prefix_of_nested_subcommand_flag_is_refused(self) -> None:
        rc, _ = parse_rc(["init", "--miss", "m"])
        self.assertEqual(rc, 2)

    def test_cli_refuses_before_touching_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "OF_NO_UPDATE_CHECK": "1"}
            proc = subprocess.run(
                [sys.executable, str(OF_PY), "init", "--miss", "m"],
                cwd=tmp, capture_output=True, text=True, env=env,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertFalse((Path(tmp) / ".orderfield").exists())


if __name__ == "__main__":
    unittest.main()
