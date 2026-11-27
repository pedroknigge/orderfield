#!/usr/bin/env python3
"""Checks that replaced contributor prose in AGENTS.md / CONTRIBUTING.md / PRINCIPLES.md.

Stdlib only. Each failure says the fix. These classes can later move into
scripts/check_agent_lessons.py: OfFlagsSpelledInFull, AgentsHubNotChangelog,
AgentsDocLinks, StdlibOnly, ShimStaysThin, SaveOrderOneWriter, NoGodSplitFiles,
CiEntry, BranchProtectionJobs, PrinciplesPointer.
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OF_PKG = SCRIPTS / "of"
SHIM = SCRIPTS / "of.py"
AGENTS = ROOT / "AGENTS.md"
PRINCIPLES = ROOT / "PRINCIPLES.md"
CONTRACT = ROOT / "references" / "principles.md"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"

# Headroom over the 754-byte floor-check shim. A command does not belong here.
SHIM_MAX_BYTES = 1_500

BANNED_DEP_FILES = (
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "setup.py",
    "setup.cfg",
    "uv.lock",
)

CRITICAL_TESTS = (
    "tests/test_kernel.py",
    "tests/test_kernel_field.py",
    "tests/test_kernel_spec.py",
    "tests/test_kernel_pack.py",
    "tests/test_kernel_regime.py",
    "tests/test_kernel_cli.py",
    "tests/test_kernel_origin.py",
    "tests/test_packaging.py",
)

GOD_SPLIT = (
    "scripts/of/field_lock.py",
    "scripts/of/field_pulse.py",
)

CONTRACT_ANCHORS = (
    "Serialized kernel mutations.",
    "One phase at a time.",
    "Escalate-up before spawn.",
    "Closed menu.",
    "Caps bind where implemented.",
    "No runtime accounting.",
    "Skill beats child.",
    "Residuals upward.",
    "The harness does not judge.",
    "ORDER moves slowly.",
    "Mission checklist",
    "Cut is optional",
)

REQUIRED_JOBS = ("test", "unused-imports", "gitleaks")
REQUIRED_OS = ("ubuntu-latest", "macos-latest")
REQUIRED_PY = ("3.11", "3.13")
SHORT_FLAG = re.compile(r"^-[^-]")
VERSION_HEADING = re.compile(r"^##\s+\d+\.\d+", re.M)
NUMBERED_RULE = re.compile(r"^\d+\.\s", re.M)
RELATIVE_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _fail(test: unittest.TestCase, fix: str) -> None:
    test.fail(fix)


def _py_files() -> list[Path]:
    found: list[Path] = []
    for base in (SCRIPTS, ROOT / "tests"):
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            found.append(path)
    return found


def _allowed_import(top: str) -> bool:
    """Stdlib, or a module that already lives in this repo (scripts/ or tests/)."""
    if top in sys.stdlib_module_names or top == "__future__":
        return True
    candidates = (
        ROOT / f"{top}.py",
        ROOT / top,
        SCRIPTS / f"{top}.py",
        SCRIPTS / top,
        ROOT / "tests" / f"{top}.py",
        ROOT / "tests" / top,
    )
    return any(path.exists() for path in candidates)


def _imported_roots(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            names = [node.module]
        else:
            continue
        for name in names:
            found.append((node.lineno, name.split(".", 1)[0]))
    return found


def _short_flags(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else None
        if name != "add_argument" and not (
            isinstance(func, ast.Name) and func.id == "add_argument"
        ):
            continue
        constants: list[ast.AST] = list(node.args)
        constants.extend(kw.value for kw in node.keywords)
        for item in constants:
            values: list[ast.Constant] = []
            if isinstance(item, ast.Constant):
                values = [item]
            elif isinstance(item, (ast.List, ast.Tuple, ast.Set)):
                values = [elt for elt in item.elts if isinstance(elt, ast.Constant)]
            for const in values:
                if isinstance(const.value, str) and SHORT_FLAG.match(const.value):
                    hits.append((node.lineno, const.value))
    return hits


class OfFlagsSpelledInFull(unittest.TestCase):
    def test_kernel_add_argument_has_no_short_option(self) -> None:
        for path in OF_PKG.rglob("*.py"):
            for lineno, flag in _short_flags(path):
                rel = path.relative_to(ROOT)
                _fail(
                    self,
                    f"spell the flag in full: replace {flag} at {rel}:{lineno} "
                    "with a --long option. Do not add a short of flag.",
                )


class AgentsHubNotChangelog(unittest.TestCase):
    def test_agents_has_no_version_heading(self) -> None:
        text = AGENTS.read_text(encoding="utf-8")
        if VERSION_HEADING.search(text):
            _fail(
                self,
                "AGENTS.md is not the changelog. Delete the version heading "
                "and put the cut in CHANGELOG.md.",
            )


class AgentsDocLinks(unittest.TestCase):
    def test_relative_links_resolve(self) -> None:
        text = AGENTS.read_text(encoding="utf-8")
        missing: list[str] = []
        for match in RELATIVE_LINK.finditer(text):
            raw = match.group(1)
            target = raw.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (ROOT / target).exists():
                missing.append(target)
        if missing:
            _fail(
                self,
                "AGENTS.md links do not exist: "
                + ", ".join(missing)
                + ". Fix the path or add the file. Do not leave a dead hub link.",
            )


class StdlibOnly(unittest.TestCase):
    def test_no_dependency_manifest_and_no_third_party_import(self) -> None:
        present = [rel for rel in BANNED_DEP_FILES if (ROOT / rel).is_file()]
        if present:
            _fail(
                self,
                "stdlib only: delete "
                + ", ".join(present)
                + ". Do not add a pip manifest, lockfile, coverage, or pytest-cov.",
            )
        for path in _py_files():
            for lineno, top in _imported_roots(path):
                if _allowed_import(top):
                    continue
                rel = path.relative_to(ROOT)
                _fail(
                    self,
                    f"stdlib only: remove third-party import {top!r} at {rel}:{lineno}. "
                    "Use the stdlib, or do not add the dependency.",
                )
        for rel in CRITICAL_TESTS:
            if not (ROOT / rel).is_file():
                _fail(
                    self,
                    f"restore {rel}. Critical paths stay in the unittest suite. "
                    "Do not replace them with a coverage package.",
                )


class ShimStaysThin(unittest.TestCase):
    def test_shim_is_floor_check_plus_cli_import(self) -> None:
        text = SHIM.read_text(encoding="utf-8")
        size = SHIM.stat().st_size
        if "from of.cli import main" not in text:
            _fail(
                self,
                "scripts/of.py must stay a shim: keep `from of.cli import main` "
                "and write the command under scripts/of/.",
            )
        tree = ast.parse(text, filename=str(SHIM))
        defs = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        if defs:
            _fail(
                self,
                "scripts/of.py defines "
                + ", ".join(defs)
                + ". Move it under scripts/of/. The shim stays a floor check plus main.",
            )
        if size > SHIM_MAX_BYTES:
            _fail(
                self,
                f"scripts/of.py is {size} bytes (cap {SHIM_MAX_BYTES}). "
                "Move the command under scripts/of/. Do not grow the shim.",
            )


class SaveOrderOneWriter(unittest.TestCase):
    def test_save_order_is_defined_only_in_field(self) -> None:
        owners: list[str] = []
        for path in SCRIPTS.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "save_order":
                    owners.append(str(path.relative_to(ROOT)))
        if owners != ["scripts/of/field.py"]:
            _fail(
                self,
                "save_order has owners "
                + (", ".join(owners) or "(none)")
                + ". Keep the one definition in scripts/of/field.py. "
                "Do not add a second ORDER writer.",
            )


class NoGodSplitFiles(unittest.TestCase):
    def test_field_lock_and_pulse_stay_in_field(self) -> None:
        present = [rel for rel in GOD_SPLIT if (ROOT / rel).is_file()]
        if present:
            _fail(
                self,
                "delete "
                + ", ".join(present)
                + ". field.py owns lock and pulse (SCOPE-GODSPLIT). "
                "Do not add field_lock.py or field_pulse.py.",
            )


class CiEntry(unittest.TestCase):
    def test_workflow_runs_the_unittest_runner_and_validate_skill(self) -> None:
        runner = (SCRIPTS / "run_tests.py").read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        if "os.cpu_count()" not in runner:
            _fail(
                self,
                "scripts/run_tests.py must keep the os.cpu_count() pool. "
                "Do not document a second test runner.",
            )
        if "python3 scripts/run_tests.py" not in workflow:
            _fail(
                self,
                "restore `python3 scripts/run_tests.py` in .github/workflows/test.yml. "
                "That is the CI unittest entry.",
            )
        if "bash scripts/validate-skill.sh" not in workflow:
            _fail(
                self,
                "restore `bash scripts/validate-skill.sh` in .github/workflows/test.yml.",
            )


class BranchProtectionJobs(unittest.TestCase):
    def test_six_required_checks_stay_in_the_workflow(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.find("\njobs:\n")
        if start < 0:
            _fail(
                self,
                "restore a jobs: block in .github/workflows/test.yml. "
                "Required checks are test (ubuntu-latest, 3.11), "
                "test (ubuntu-latest, 3.13), test (macos-latest, 3.11), "
                "test (macos-latest, 3.13), gitleaks, unused-imports.",
            )
        jobs = re.findall(r"(?m)^  ([a-z][a-z0-9-]*):\s*$", text[start:])
        missing = [name for name in REQUIRED_JOBS if name not in jobs]
        if missing or any(os_name not in text for os_name in REQUIRED_OS):
            _fail(
                self,
                "required checks dropped from .github/workflows/test.yml. "
                "Restore jobs "
                + ", ".join(REQUIRED_JOBS)
                + " on "
                + " and ".join(REQUIRED_OS)
                + " × Python "
                + " and ".join(REQUIRED_PY)
                + ". Do not delete a job to silence this test.",
            )
        for version in REQUIRED_PY:
            if f'"{version}"' not in text:
                _fail(
                    self,
                    f"restore Python {version} on the test matrix in "
                    ".github/workflows/test.yml. Required checks are "
                    "ubuntu/macos × 3.11/3.13, gitleaks, and unused-imports.",
                )


class PrinciplesPointer(unittest.TestCase):
    def test_short_file_points_at_the_contract(self) -> None:
        short = PRINCIPLES.read_text(encoding="utf-8")
        contract = CONTRACT.read_text(encoding="utf-8")
        if "references/principles.md" not in short:
            _fail(
                self,
                "PRINCIPLES.md must point at references/principles.md. "
                "Do not fork a second contract.",
            )
        if NUMBERED_RULE.search(short):
            _fail(
                self,
                "PRINCIPLES.md grew a numbered list. Delete it. "
                "Edit the invariant in references/principles.md.",
            )
        missing = [anchor for anchor in CONTRACT_ANCHORS if anchor not in contract]
        if missing:
            _fail(
                self,
                "references/principles.md dropped "
                + "; ".join(missing)
                + ". Restore the invariant there. Do not paste it back into PRINCIPLES.md.",
            )


if __name__ == "__main__":
    unittest.main()
