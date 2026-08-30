#!/usr/bin/env python3
"""Install + version sync against the shipped package."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OF_PY = ROOT / "scripts" / "of.py"
INSTALL = ROOT / "install.sh"


def run(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=merged,
    )


class VersionSync(unittest.TestCase):
    def test_version_files_agree(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## {ver}", changelog)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f'version: "{ver}"', skill)

    def test_docs_name_agy(self) -> None:
        for rel in ("SKILL.md", "references/adapters.md", "README.md", "AGENTS.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("agy", text, rel)
            self.assertNotIn("--adapter antigravity", text)


class InstallScript(unittest.TestCase):
    def test_empty_root_gets_agents_fallback(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        proc = run(tmp, "bash", str(INSTALL), str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        dest = tmp / ".agents" / "skills" / "orderfield"
        self.assertTrue((dest / "SKILL.md").is_file(), dest)
        self.assertTrue((dest / "scripts" / "of.py").is_file(), dest)
        self.assertTrue((dest / "SLAVE.md").is_file(), dest)
        self.assertFalse((tmp / ".claude").exists())
        self.assertFalse((tmp / ".codex").exists())
        self.assertFalse((tmp / ".agy").exists())
        self.assertFalse((tmp / ".gemini").exists())
        # project/--root: hermetic of symlink under base, not real HOME
        link = tmp / ".local" / "bin" / "of"
        self.assertTrue(link.is_symlink(), proc.stdout)
        self.assertEqual(link.resolve(), (dest / "scripts" / "of.py").resolve())
        self.assertIn("of:", proc.stdout)

    def test_existing_harness_dir_also_gets_generic(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-h-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".claude").mkdir()
        proc = run(tmp, "bash", str(INSTALL), str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((tmp / ".claude" / "skills" / "orderfield" / "SKILL.md").is_file())
        self.assertTrue((tmp / ".agents" / "skills" / "orderfield" / "SKILL.md").is_file())

    def test_generic_only_flag(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-g-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".claude").mkdir()
        proc = run(tmp, "bash", str(INSTALL), "--generic", "--root", str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((tmp / ".agents" / "skills" / "orderfield" / "SKILL.md").is_file())
        self.assertFalse((tmp / ".claude" / "skills").exists())
        link = tmp / ".local" / "bin" / "of"
        self.assertTrue(link.is_symlink())
        self.assertEqual(
            link.resolve(),
            (tmp / ".agents" / "skills" / "orderfield" / "scripts" / "of.py").resolve(),
        )

    def test_gemini_dirs_get_agy_skill_not_dot_agy(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-agy-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".gemini" / "config").mkdir(parents=True)
        (tmp / ".gemini" / "antigravity-cli").mkdir(parents=True)
        proc = run(tmp, "bash", str(INSTALL), str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(
            (tmp / ".gemini" / "config" / "skills" / "orderfield" / "SKILL.md").is_file()
        )
        self.assertTrue(
            (
                tmp / ".gemini" / "antigravity-cli" / "skills" / "orderfield" / "SKILL.md"
            ).is_file()
        )
        self.assertTrue((tmp / ".agents" / "skills" / "orderfield" / "SKILL.md").is_file())
        self.assertFalse((tmp / ".agy").exists())

    def test_generic_only_skips_gemini_agy_dests(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-agy-g-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".gemini" / "config").mkdir(parents=True)
        (tmp / ".gemini" / "antigravity-cli").mkdir(parents=True)
        proc = run(tmp, "bash", str(INSTALL), "--generic", "--root", str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((tmp / ".agents" / "skills" / "orderfield" / "SKILL.md").is_file())
        self.assertFalse((tmp / ".gemini" / "config" / "skills").exists())
        self.assertFalse((tmp / ".gemini" / "antigravity-cli" / "skills").exists())
        self.assertFalse((tmp / ".agy").exists())

    def test_global_agy_on_path_creates_gemini_dests_not_dot_agy(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-agy-path-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        bindir = tmp / "bin"
        bindir.mkdir()
        fake = bindir / "agy"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(0o755)
        env = {
            "HOME": str(tmp),
            "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        proc = run(tmp, "bash", str(INSTALL), "--global", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(
            (tmp / ".gemini" / "config" / "skills" / "orderfield" / "SKILL.md").is_file()
        )
        self.assertTrue(
            (
                tmp / ".gemini" / "antigravity-cli" / "skills" / "orderfield" / "SKILL.md"
            ).is_file()
        )
        self.assertTrue((tmp / ".agents" / "skills" / "orderfield" / "SKILL.md").is_file())
        self.assertFalse((tmp / ".agy").exists())
        dest_of = tmp / ".agents" / "skills" / "orderfield" / "scripts" / "of.py"
        link = tmp / ".local" / "bin" / "of"
        self.assertTrue(link.is_symlink(), proc.stdout)
        self.assertEqual(link.resolve(), dest_of.resolve())
        # Must not point at the install source checkout (adversary E / cut-plan).
        self.assertNotEqual(link.resolve(), (ROOT / "scripts" / "of.py").resolve())
        self.assertIn("Ensure ~/.local/bin is on your PATH", proc.stdout)

    def test_global_uninstall_removes_of_symlink(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-un-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        env = {"HOME": str(tmp)}
        proc = run(tmp, "bash", str(INSTALL), "--global", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        link = tmp / ".local" / "bin" / "of"
        self.assertTrue(link.is_symlink())
        proc = run(tmp, "bash", str(INSTALL), "--global", "--uninstall", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(link.exists(), proc.stdout)
        self.assertIn("removed", proc.stdout)

    def test_root_uninstall_removes_hermetic_of_symlink(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-un-root-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        proc = run(tmp, "bash", str(INSTALL), "--root", str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        link = tmp / ".local" / "bin" / "of"
        self.assertTrue(link.is_symlink())
        proc = run(tmp, "bash", str(INSTALL), "--root", str(tmp), "--uninstall")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(link.exists(), proc.stdout)

    def test_install_sh_agy_dests_are_gemini_not_dot_agy(self) -> None:
        src = INSTALL.read_text(encoding="utf-8")
        self.assertIn(".gemini/config/skills", src)
        self.assertIn(".gemini/antigravity-cli/skills", src)
        self.assertNotIn("/.agy/", src)
        self.assertNotRegex(src, r"\$base/\.agy")
        harnesses = src.split("KNOWN_HARNESSES=", 1)[1].split(")", 1)[0]
        self.assertNotIn("agy", harnesses)
        self.assertNotIn("antigravity", harnesses)
        # PATH symlink targets installed dest, not $SRC (adversary E).
        self.assertIn("of_installed_kernel", src)
        self.assertIn('"$base/.agents/skills/$NAME/scripts/of.py"', src)
        self.assertNotRegex(
            src,
            r'ln -sf\s+"\$SRC/scripts/of\.py"',
        )


class PhaseMdEnglish(unittest.TestCase):
    def test_init_writes_english_phase_md(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-phase-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        proc = run(
            tmp,
            sys.executable,
            str(OF_PY),
            "init",
            "--mission",
            "architecture for a pricing tool",
            "--phase",
            "explore",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = (tmp / ".orderfield" / "PHASE.md").read_text(encoding="utf-8")
        self.assertIn("# Phase:", text)
        self.assertIn("Mission:", text)
        self.assertNotIn("Fase:", text)
        self.assertNotIn("Mision:", text)

    def test_patch_rewrites_english_phase_md(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-phase-patch-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        proc = run(
            tmp,
            sys.executable,
            str(OF_PY),
            "init",
            "--mission",
            "architecture for a pricing tool",
            "--phase",
            "explore",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = run(
            tmp,
            sys.executable,
            str(OF_PY),
            "patch",
            "--mission",
            "patched mission",
            "--done-when",
            "patched criterion",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = (tmp / ".orderfield" / "PHASE.md").read_text(encoding="utf-8")
        self.assertIn("# Phase:", text)
        self.assertIn("patched mission", text)
        self.assertIn("patched criterion", text)
        self.assertNotIn("Fase:", text)


class ValidateSkill(unittest.TestCase):
    def test_validate_skill_exits_zero(self) -> None:
        script = ROOT / "scripts" / "validate-skill.sh"
        self.assertTrue(script.is_file())
        mode = script.stat().st_mode
        if not (mode & stat.S_IXUSR):
            script.chmod(mode | stat.S_IXUSR)
        proc = run(ROOT, "bash", str(script))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
