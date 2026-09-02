#!/usr/bin/env python3
"""Install + version sync against the shipped package."""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tarfile
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
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f'version: "{ver}"', alias)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"<strong>v{ver}</strong>", readme)
        self.assertIn(f"skill-{ver}-", readme)
        self.assertIn("--full-depth -s '*' -a '*'", readme)
        for rel in (
            "docs/architecture.md",
            "docs/audit/claims-matrix.md",
            "docs/features/kernel/README.md",
            "docs/features/adapters/README.md",
        ):
            self.assertIn(f"`{ver}`", (ROOT / rel).read_text(encoding="utf-8"), rel)
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("docs/roadmap.md", agents)
        roadmap = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
        for required in ("0.5.0", "Qwen Code", "trust profiles", "of doctor", "scale_up"):
            self.assertIn(required, roadmap)

    def test_docs_name_agy(self) -> None:
        for rel in ("SKILL.md", "references/adapters.md", "README.md", "AGENTS.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("agy", text, rel)
            self.assertNotIn("--adapter antigravity", text)

    def test_publish_verification_uses_supported_gh_release_fields(self) -> None:
        publish = (ROOT / "PUBLISH.md").read_text(encoding="utf-8")
        self.assertNotIn("isLatest", publish)
        self.assertIn('--json tagName --jq .tagName', publish)
        self.assertIn('--json publishedAt --jq .publishedAt', publish)
        self.assertIn("url,tagName,isDraft,isPrerelease,publishedAt", publish)
        self.assertIn("SHA256SUMS", publish)
        self.assertIn("git archive", publish)
        self.assertIn("gh release upload", publish)
        self.assertIn("SHA-256", publish)
        self.assertNotIn(
            "raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh",
            publish,
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh",
            readme,
        )
        self.assertIn("SHA-256", readme)
        self.assertIn("releases/download", readme)
        self.assertIn("SHA256SUMS", readme)

    def test_slave_heartbeat_is_activity_evidence_not_process_health(self) -> None:
        slave = (ROOT / "SLAVE.md").read_text(encoding="utf-8")
        self.assertIn("activity evidence for `of pulse`", slave)
        self.assertIn("shared-repo product mtime", slave)
        self.assertIn("not process health or per-child write attribution", slave)
        self.assertNotIn("liveness is derived", slave)


class InstallScript(unittest.TestCase):
    def test_literal_project_install_uses_stable_source_and_absolute_link(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-project-source-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        source = tmp / "orderfield"
        shutil.copytree(
            ROOT,
            source,
            ignore=shutil.ignore_patterns(
                ".git",
                ".orderfield",
                ".agents",
                ".claude",
                ".codex",
                ".cursor",
                ".opencode",
                ".grok",
                ".gemini",
                ".local",
                "__pycache__",
                "vibe-proof-audit-report.*",
            ),
        )

        proc = run(source, "bash", "./install.sh", "--project")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        dest = source / ".agents" / "skills" / "orderfield"
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertFalse((dest / ".agents").exists(), proc.stdout)
        link = source / ".local" / "bin" / "of"
        self.assertTrue(link.is_symlink(), proc.stdout)
        self.assertTrue(link.exists(), proc.stdout)
        self.assertEqual(link.resolve(), (dest / "scripts" / "of.py").resolve())

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
        self.assertIn("--full-depth -s '*'", src)
        self.assertIn("A harness name alone or one ordinary", src)
        self.assertIn("DEFAULT_VERSION=", src)
        self.assertIn("fetch_pinned_source", src)
        self.assertIn("SHA-256", src)
        self.assertNotIn("git clone", src)
        self.assertNotIn(
            "raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh",
            src,
        )

    def test_install_sh_has_no_dev_fd_process_substitution(self) -> None:
        # CLI-001: dest iteration must not use < <(cmd) / /dev/fd.
        src = INSTALL.read_text(encoding="utf-8")
        self.assertNotRegex(src, r"<\s*<\s*\(")
        self.assertNotRegex(src, r"(^|[^<])<\(")
        self.assertNotRegex(src, r">\(")
        self.assertNotIn("/dev/fd", src)
        self.assertIn("agy_dests", src)
        self.assertIn("$(agy_dests)", src)


class InstallPin(unittest.TestCase):
    """INSTALL-001: tag-pinned remote install with SHA-256 verify."""

    def _detached_installer(self, tmp: Path) -> Path:
        script = tmp / "install.sh"
        shutil.copy(INSTALL, script)
        return script

    def _archive(self, tmp: Path, version: str) -> Path:
        tree = tmp / "tree"
        (tree / "scripts").mkdir(parents=True)
        (tree / "of").mkdir()
        (tree / "SKILL.md").write_text(
            f'---\nname: orderfield\nversion: "{version}"\n---\n# skill\n',
            encoding="utf-8",
        )
        (tree / "of" / "SKILL.md").write_text(
            "---\nname: of\nalias-of: orderfield\n---\n",
            encoding="utf-8",
        )
        of_py = tree / "scripts" / "of.py"
        of_py.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
        of_py.chmod(0o755)
        archive = tmp / f"orderfield-{version}.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(tree, arcname=f"orderfield-{version}")
        return archive

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _run_detached(
        self,
        tmp: Path,
        dest: Path,
        env: dict[str, str],
        extra_args: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        script = self._detached_installer(tmp)
        merged = {
            "HOME": str(tmp / "home"),
            "ORDERFIELD_REF": env.get("ORDERFIELD_REF", "v0.0.0-pin"),
            "ORDERFIELD_VERSION": env.get("ORDERFIELD_VERSION", "0.0.0-pin"),
        }
        merged.update(env)
        return run(
            tmp,
            "bash",
            str(script),
            "--root",
            str(dest),
            *extra_args,
            env=merged,
        )

    def test_default_pin_matches_version_file(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        src = INSTALL.read_text(encoding="utf-8")
        self.assertIn(f'DEFAULT_VERSION="{ver}"', src)

    def test_remote_archive_matching_sha256_installs(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-pin-ok-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = tmp / "dest"
        archive = self._archive(tmp, "0.0.0-pin")
        digest = self._sha256(archive)
        proc = self._run_detached(
            tmp,
            dest,
            {
                "ORDERFIELD_ARCHIVE": str(archive),
                "ORDERFIELD_SHA256": digest,
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        skill = dest / ".agents" / "skills" / "orderfield"
        self.assertTrue((skill / "SKILL.md").is_file(), proc.stdout)
        self.assertTrue((skill / "scripts" / "of.py").is_file())
        self.assertIn("copied to", proc.stdout)

    def test_remote_archive_matching_sha256sums_file_installs(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-pin-sums-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = tmp / "dest"
        archive = self._archive(tmp, "0.0.0-pin")
        digest = self._sha256(archive)
        sums = tmp / "SHA256SUMS"
        sums.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
        proc = self._run_detached(
            tmp,
            dest,
            {
                "ORDERFIELD_ARCHIVE": str(archive),
                "ORDERFIELD_SHA256SUMS": str(sums),
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(
            (dest / ".agents" / "skills" / "orderfield" / "SKILL.md").is_file()
        )

    def test_remote_archive_sha256_mismatch_refuses(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-pin-bad-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = tmp / "dest"
        archive = self._archive(tmp, "0.0.0-pin")
        proc = self._run_detached(
            tmp,
            dest,
            {
                "ORDERFIELD_ARCHIVE": str(archive),
                "ORDERFIELD_SHA256": "0" * 64,
            },
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("SHA-256 mismatch", proc.stderr)
        self.assertFalse((dest / ".agents" / "skills" / "orderfield").exists())

    def test_remote_archive_without_checksum_refuses(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-pin-nocheck-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = tmp / "dest"
        archive = self._archive(tmp, "0.0.0-pin")
        proc = self._run_detached(
            tmp,
            dest,
            {"ORDERFIELD_ARCHIVE": str(archive)},
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("ORDERFIELD_SHA256", proc.stderr)
        self.assertFalse((dest / ".agents" / "skills" / "orderfield").exists())

    def test_unsigned_mutable_main_refuses(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-pin-main-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = tmp / "dest"
        archive = self._archive(tmp, "0.0.0-pin")
        proc = self._run_detached(
            tmp,
            dest,
            {
                "ORDERFIELD_REF": "main",
                "ORDERFIELD_VERSION": "0.0.0-pin",
                "ORDERFIELD_ARCHIVE": str(archive),
                "ORDERFIELD_SHA256": self._sha256(archive),
            },
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("refusing unsigned mutable ref", proc.stderr)
        self.assertFalse((dest / ".agents" / "skills" / "orderfield").exists())


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


class VersionedDescription(unittest.TestCase):
    def test_description_preview_starts_with_version(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f"description: v{ver} —", skill)


class RepositoryAliasSkill(unittest.TestCase):
    def _install(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="of-alias-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        proc = run(tmp, "bash", str(INSTALL), str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return tmp

    def test_alias_installed_next_to_skill(self) -> None:
        tmp = self._install()
        alias = tmp / ".agents" / "skills" / "of" / "SKILL.md"
        self.assertTrue(alias.is_file(), alias)
        body = alias.read_text(encoding="utf-8")
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertIn("name: of", body)
        self.assertIn(f"description: v{ver} —", body)
        self.assertIn("alias-of: orderfield", body)
        self.assertIn("../orderfield/SKILL.md", body)
        self.assertEqual(body, (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8"))

    def test_source_package_owns_npx_discoverable_alias(self) -> None:
        alias = ROOT / "of" / "SKILL.md"
        self.assertTrue(alias.is_file(), alias)
        body = alias.read_text(encoding="utf-8")
        self.assertTrue(body.startswith("---\nname: of\n"))
        self.assertIn("alias-of: orderfield", body)
        self.assertIn("Do not trigger for a harness name alone", body)

    def test_uninstall_removes_alias_too(self) -> None:
        tmp = self._install()
        alias_dir = tmp / ".agents" / "skills" / "of"
        self.assertTrue(alias_dir.is_dir())
        proc = run(tmp, "bash", str(INSTALL), "--uninstall", "--root", str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(alias_dir.exists())
        self.assertFalse((tmp / ".agents" / "skills" / "orderfield").exists())
