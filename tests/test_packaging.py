#!/usr/bin/env python3
"""Install + version sync against the shipped package."""
from __future__ import annotations

import hashlib
import importlib.util
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
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from living_map import (  # noqa: E402
    LivingMap,
    SkillEfficiencyMix,
    SkillHarnessMix,
    SkillRunbookPath,
)
from skill_surface import SkillSurface  # noqa: E402


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
        self.assertIn("print the last 1–3 lines under `running`", slave)
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
        self.assertTrue(
            (tmp / ".gemini" / "skills" / "orderfield" / "SKILL.md").is_file()
        )
        self.assertTrue((tmp / ".agents" / "skills" / "orderfield" / "SKILL.md").is_file())
        self.assertFalse((tmp / ".agy").exists())

    def test_gemini_home_gets_shared_agy_skill(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-agy-shared-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".gemini").mkdir(parents=True)
        proc = run(tmp, "bash", str(INSTALL), str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(
            (tmp / ".gemini" / "skills" / "orderfield" / "SKILL.md").is_file()
        )
        self.assertTrue((tmp / ".gemini" / "skills" / "of" / "SKILL.md").is_file())
        self.assertFalse((tmp / ".gemini" / "antigravity-cli" / "skills").exists())
        self.assertFalse((tmp / ".gemini" / "config" / "skills").exists())
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
        self.assertFalse((tmp / ".gemini" / "skills" / "orderfield").exists())
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
        self.assertFalse(
            (tmp / ".gemini" / "config" / "skills" / "orderfield").exists()
        )
        self.assertTrue(
            (
                tmp / ".gemini" / "antigravity-cli" / "skills" / "orderfield" / "SKILL.md"
            ).is_file()
        )
        self.assertTrue(
            (tmp / ".gemini" / "skills" / "orderfield" / "SKILL.md").is_file()
        )
        self.assertTrue((tmp / ".gemini" / "skills" / "of" / "SKILL.md").is_file())
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
        self.assertIn(".gemini/skills", src)
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
        self.assertIn("--from-release", src)
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

    def test_from_release_ignores_local_checkout(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-install-from-rel-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = tmp / "dest"
        archive = self._archive(tmp, "0.0.0-pin")
        digest = self._sha256(archive)
        checkout_ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        proc = run(
            tmp,
            "bash",
            str(INSTALL),
            "--root",
            str(dest),
            "--from-release",
            env={
                "HOME": str(tmp / "home"),
                "ORDERFIELD_REF": "v0.0.0-pin",
                "ORDERFIELD_VERSION": "0.0.0-pin",
                "ORDERFIELD_ARCHIVE": str(archive),
                "ORDERFIELD_SHA256": digest,
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        skill = dest / ".agents" / "skills" / "orderfield" / "SKILL.md"
        body = skill.read_text(encoding="utf-8")
        self.assertIn('version: "0.0.0-pin"', body)
        self.assertNotIn(checkout_ver, body)

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


def _load_packaging_bump() -> object:
    spec = importlib.util.spec_from_file_location(
        "of_check_packaging_bump",
        ROOT / "scripts" / "check_packaging_bump.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PackagingBump


PackagingBump = _load_packaging_bump()


class PackagingBumpDiscipline(unittest.TestCase):
    """One VERSION per proven invariant. Packaging/docs-only lockstep dies."""

    REAL_CUT = (
        "# Changelog\n\n"
        "## 9.9.9\n\n"
        "Real cut. Same 0.6 line.\n\n"
        "- **Proof:** a kernel or public-surface change landed.\n"
        "- Packaging: VERSION 9.9.9; skill/alias description preview "
        "`v9.9.9 — …`. `install.sh` `DEFAULT_VERSION` in lockstep.\n"
    )
    PACKAGING_ONLY = (
        "# Changelog\n\n"
        "## 9.9.9\n\n"
        "Packaging identity only.\n\n"
        "- Packaging: VERSION 9.9.9; skill/alias description preview "
        "`v9.9.9 — …`. `install.sh` `DEFAULT_VERSION` in lockstep.\n"
    )
    DOCS_ONLY = (
        "# Changelog\n\n"
        "## 9.9.9\n\n"
        "Docs wording only.\n\n"
        "- Docs: README badge color.\n"
        "- Packaging: VERSION 9.9.9; skill/alias description preview "
        "`v9.9.9 — …`. `install.sh` `DEFAULT_VERSION` in lockstep.\n"
    )
    UNPROVEN = (
        "# Changelog\n\n"
        "## 9.9.9\n\n"
        "Caption without proof.\n\n"
        "- Feature: did a thing.\n"
        "- Packaging: VERSION 9.9.9; skill/alias description preview "
        "`v9.9.9 — …`. `install.sh` `DEFAULT_VERSION` in lockstep.\n"
    )
    HISTORICAL_WITHOUT_PROOF = (
        "# Changelog\n\n"
        "## 9.9.9\n\n"
        "Current proven cut.\n\n"
        "- **Proof:** `PackagingBumpDiscipline` current heading.\n"
        "- Packaging: VERSION 9.9.9; skill/alias description preview "
        "`v9.9.9 — …`. `install.sh` `DEFAULT_VERSION` in lockstep.\n"
        "\n"
        "## 1.0.0\n\n"
        "- Feature: shipped before the Proof marker existed.\n"
    )

    def _stage(self, changelog: str, version: str = "9.9.9") -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="of-pack-bump-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "VERSION").write_text(version + "\n", encoding="utf-8")
        (tmp / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        return tmp

    def test_repo_passes(self) -> None:
        self.assertEqual(PackagingBump.errors(ROOT), [])

    def test_cli_exits_zero_on_repo(self) -> None:
        script = ROOT / "scripts" / "check_packaging_bump.py"
        proc = run(ROOT, sys.executable, str(script), str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertIn(f"OK packaging bump {ver}", proc.stdout)

    def test_real_cut_plus_lockstep_passes(self) -> None:
        tmp = self._stage(self.REAL_CUT)
        self.assertEqual(PackagingBump.errors(tmp), [])

    def test_packaging_only_fails(self) -> None:
        tmp = self._stage(self.PACKAGING_ONLY)
        errs = PackagingBump.errors(tmp)
        self.assertTrue(any("packaging-only VERSION 9.9.9" in e for e in errs), errs)
        script = ROOT / "scripts" / "check_packaging_bump.py"
        proc = run(tmp, sys.executable, str(script), str(tmp))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("packaging-only VERSION 9.9.9", proc.stderr)

    def test_duplicate_version_heading_fails(self) -> None:
        text = self.REAL_CUT + "\n## 9.9.9\n\n- **Again:** same cut twice.\n"
        tmp = self._stage(text)
        errs = PackagingBump.errors(tmp)
        self.assertTrue(any("duplicate VERSION 9.9.9" in e for e in errs), errs)

    def test_heading_mismatch_fails(self) -> None:
        tmp = self._stage(self.REAL_CUT, version="0.0.1")
        errs = PackagingBump.errors(tmp)
        self.assertTrue(
            any("first heading 9.9.9 != VERSION 0.0.1" in e for e in errs),
            errs,
        )

    def test_docs_only_current_fails(self) -> None:
        tmp = self._stage(self.DOCS_ONLY)
        errs = PackagingBump.errors(tmp)
        self.assertTrue(any("docs-only VERSION 9.9.9" in e for e in errs), errs)
        script = ROOT / "scripts" / "check_packaging_bump.py"
        proc = run(tmp, sys.executable, str(script), str(tmp))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("docs-only VERSION 9.9.9", proc.stderr)

    def test_unproven_current_fails(self) -> None:
        tmp = self._stage(self.UNPROVEN)
        errs = PackagingBump.errors(tmp)
        self.assertTrue(any("unproven VERSION 9.9.9" in e for e in errs), errs)
        script = ROOT / "scripts" / "check_packaging_bump.py"
        proc = run(tmp, sys.executable, str(script), str(tmp))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("unproven VERSION 9.9.9", proc.stderr)

    def test_historical_without_proof_still_ok(self) -> None:
        tmp = self._stage(self.HISTORICAL_WITHOUT_PROOF)
        self.assertEqual(PackagingBump.errors(tmp), [])

    def test_policy_docs_name_the_gate(self) -> None:
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        publish = (ROOT / "PUBLISH.md").read_text(encoding="utf-8")
        evals = (ROOT / "evals" / "README.md").read_text(encoding="utf-8")
        self.assertIn("One VERSION per real cut", contributing)
        self.assertIn("proven user-facing or kernel invariant", contributing)
        self.assertIn("10 tags/day", contributing)
        self.assertIn("check_packaging_bump.py", contributing)
        self.assertIn("PackagingBumpDiscipline", contributing)
        self.assertIn("one VERSION per real cut", publish)
        self.assertIn("proven invariant", publish)
        self.assertIn("10 tags/day", publish)
        self.assertIn("GitHub release tag", publish)
        self.assertIn("check_packaging_bump.py", publish)
        self.assertIn("PackagingBumpDiscipline", evals)
        self.assertIn("check_packaging_bump.py", evals)
        self.assertIn("proven invariant", evals)
        skill = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = skill.split("## What to type next", 1)[1].split(
            "## When to use", 1
        )[0]
        for text in (table, alias, appendix):
            folded = text.casefold()
            self.assertIn("proven invariant", folded)
            self.assertIn("10-tags", folded)
            self.assertIn("check_packaging_bump.py", text)
            self.assertIn("**Proof:**", text)


class ReadmeProductSurface(unittest.TestCase):
    """README opens with problem → feature. Haken analogy stays below."""

    def test_use_cases_before_kernel_and_haken(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        folded = text.casefold()
        use = text.index("# Typical problems")
        midflight = text.index("## Mid-flight, the plan can change without dying")
        install = text.index("## Install")
        kernel = text.index("## What the kernel enforces")
        haken = folded.index("haken")
        self.assertLess(use, midflight)
        self.assertLess(midflight, install)
        self.assertLess(use, install)
        self.assertLess(use, kernel)
        self.assertLess(use, haken)
        self.assertGreater(haken, kernel)
        self.assertIn("references/principles.md", text)
        self.assertIn("analogy, not a science claim", folded)
        kernel_block = text[kernel : text.index("## Generic mode")]
        self.assertIn("when work goes through `of`", kernel_block)
        self.assertIn("remain protocol", kernel_block)
        self.assertIn("slaving-by-contract", kernel_block.casefold())
        self.assertIn("not a jail", kernel_block.casefold())
        hero = text[:install]
        for needle in (
            "Anyone can persist a plan. Only the leader may change it.",
            "The brief lives on disk as SPEC",
            "of resume",
            "of handoff",
            "Close is proof",
            "CLOSE.json",
            ".orderfield/",
            "When not",
            "## Mid-flight, the plan can change without dying",
            "You intervene.",
            "A child reports the field is wrong.",
            "A child finds something the plan missed.",
            "sibling fields",
            "cheap vs frontier",
            "A child residual cannot rewrite",
        ):
            self.assertIn(needle, hero)
        install_block = text[install:text.index("## Uninstall")]
        chunks = install_block.split("```")
        lead, first_fence = chunks[0], chunks[1]
        self.assertTrue(first_fence.startswith("bash"), first_fence[:20])
        self.assertIn("SHA256SUMS", first_fence)
        self.assertIn("releases/download", first_fence)
        self.assertIn("SHA-256", first_fence)
        self.assertNotIn("npx skills add pedroknigge/orderfield", first_fence)
        self.assertIn("SHA-256", lead)
        self.assertIn("unpinned", lead.casefold())
        self.assertIn("npx skills add", lead.casefold())
        self.assertIn("not", lead.casefold())
        self.assertIn("trusted", lead.casefold())
        npx_cmd = install_block.index("npx skills add pedroknigge/orderfield")
        self.assertLess(install_block.index("SHA256SUMS"), npx_cmd)
        self.assertLess(install_block.index("releases/download"), npx_cmd)
        self.assertLess(install_block.index("./install.sh"), npx_cmd)
        self.assertIn("first close", install_block.casefold())
        self.assertIn("unpinned", install_block.casefold())
        self.assertIn("not the trusted", install_block.casefold())
        self.assertIn("SHA-256", install_block)
        compared = text[text.index("## Compared-to"):]
        self.assertIn("planning-with-files", compared)
        self.assertIn("refuse_child_forge", compared)
        self.assertIn("authority kernel through `of`", compared)
        self.assertIn("cooperative CLI, not a jail", compared)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        appendix = (ROOT / "references" / "skill-appendix.md").read_text(encoding="utf-8")
        self.assertIn("typical problems", skill.casefold())
        self.assertIn("typical problems", alias.casefold())
        self.assertIn("mid-flight", skill.casefold())
        self.assertIn("mid-flight", alias.casefold())
        self.assertIn("planning-with-files", skill.casefold())
        self.assertIn("planning-with-files", alias.casefold())
        self.assertIn("only the leader may change it", skill.casefold())
        self.assertIn("only the leader may change it", alias.casefold())
        self.assertIn("first close", skill.casefold())
        self.assertIn("first close", alias.casefold())
        for surface, label in (
            (skill, "SKILL.md"),
            (alias, "of/SKILL.md"),
            (appendix, "references/skill-appendix.md"),
        ):
            folded = surface.casefold()
            self.assertIn("sha-256", folded, label)
            self.assertIn("unpinned", folded, label)
            self.assertIn("npx", folded, label)
            self.assertIn("not trusted", folded, label)
        self.assertIn("planning-with-files", appendix.casefold())
        self.assertIn("when work goes through `of`", skill)
        self.assertIn("remain protocol", skill)
        self.assertIn("slaving-by-contract through `of`", alias)
        self.assertIn("slaving-by-contract through `of`", appendix)
        self.assertIn("not a jail", alias.casefold())
        self.assertIn("not a jail", appendix.casefold())


class FieldEvidenceHonesty(unittest.TestCase):
    """In-repo lab proof is re-runnable; external dogfood stays Partial."""

    LAB = "in-repo lab"
    EVAL = "of eval --strict --kernel"
    PARTIAL = "external dogfood stays partial (c-153)"
    NO_INVENT = "do not invent case studies"

    @staticmethod
    def surfaces() -> dict[str, str]:
        return {
            "SKILL.md": SkillSurface.core(ROOT),
            "of/SKILL.md": SkillSurface.alias(ROOT),
            "references/skill-appendix.md": SkillSurface.appendix(ROOT),
            "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
            "docs/external-brief.md": (ROOT / "docs" / "external-brief.md").read_text(
                encoding="utf-8"
            ),
        }

    def test_surfaces_teach_lab_vs_partial_dogfood(self) -> None:
        for rel, text in self.surfaces().items():
            folded = text.casefold()
            self.assertIn(self.LAB, folded, rel)
            self.assertIn(self.EVAL, text, rel)
            self.assertIn(self.PARTIAL, folded, rel)
            self.assertIn(self.NO_INVENT, folded, rel)

    def test_claims_matrix_keeps_external_dogfood_partial(self) -> None:
        matrix = (ROOT / "docs" / "audit" / "claims-matrix.md").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            matrix,
            r"\| C-153 \|.*\| normal \| Partial \|",
        )
        self.assertIn("in-repo lab", matrix.casefold())
        self.assertIn("no invented customers", matrix.casefold())


class SkillLeaderInitiative(unittest.TestCase):
    """Leader must propose cheap vs frontier in chat before a multi-role pack."""

    def test_skill_proposes_before_pack_and_alias_mirrors(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        propose_at = table.casefold().index("propose in chat")
        pack_at = table.index("--model-tier")
        self.assertLess(propose_at, pack_at)
        self.assertIn("must propose", skill.casefold())
        self.assertIn("never silent switch", skill.casefold())
        self.assertIn("must propose", alias.casefold())
        self.assertIn("cheap", alias.casefold())
        self.assertIn("frontier", alias.casefold())
        hero = readme[: readme.index("## Install")]
        self.assertIn("cheap vs frontier", hero.casefold())
        self.assertIn("confirm", hero.casefold())


class SkillHarnessAsk(unittest.TestCase):
    """Leader must ask same-harness vs multi-harness mix before pack."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    @staticmethod
    def folded(text: str) -> str:
        return text.casefold()

    def test_skill_asks_before_pack_and_alias_mirrors(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        table = self.folded(self.table(skill))
        ask_at = table.index("ask in chat")
        detect_at = table.index("of detect")
        self.assertLess(ask_at, detect_at)
        self.assertIn("same-harness", table)
        self.assertIn("multi-harness", table)
        self.assertIn("must ask", self.folded(skill))
        self.assertIn("never silent mix", self.folded(skill))
        self.assertIn("must ask", self.folded(alias))
        self.assertIn("same-harness", self.folded(alias))
        self.assertIn("multi-harness", self.folded(alias))
        self.assertIn("of detect", self.folded(alias))
        hero = self.folded(readme[: readme.index("## Install")])
        self.assertIn("same-harness", hero)
        self.assertIn("multi-harness", hero)
        self.assertIn("of detect", hero)


class SkillModelCatalogConsult(unittest.TestCase):
    """Leader consults the living catalog before cheap/frontier or mix."""

    def test_skill_consults_catalog_before_propose_and_alias_mirrors(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        folded = table.casefold()
        consult_at = folded.index("consult")
        propose_at = folded.index("propose in chat")
        ask_at = folded.index("ask in chat")
        self.assertLess(consult_at, propose_at)
        self.assertLess(consult_at, ask_at)
        self.assertIn("model-catalog", folded)
        self.assertIn("smarter", folded)
        self.assertIn("budget.tokens", folded)
        alias_fold = alias.casefold()
        self.assertIn("consult", alias_fold)
        self.assertIn("model-catalog", alias_fold)
        self.assertIn("smarter", alias_fold)
        hero = readme[: readme.index("## Install")].casefold()
        self.assertIn("model catalog", hero)
        self.assertIn("cheap vs frontier", hero)


class ModelCatalogHonesty(unittest.TestCase):
    """Catalog is sourced or unknown. Not IQ ranks. Not budget.tokens."""

    def test_catalog_is_honest_and_lockstep(self) -> None:
        from of.model_catalog import ModelCatalog

        errors = ModelCatalog.errors(ROOT)
        self.assertEqual(errors, [])
        doc = ModelCatalog.load(ROOT)
        models = ModelCatalog.models(doc)
        self.assertGreaterEqual(len(models), 8)
        harnesses = {str(row["harness"]) for row in models}
        for name in ("claude", "codex", "cursor", "grok", "agy"):
            self.assertIn(name, harnesses)
        known = [row for row in models if row.get("price_known")]
        self.assertTrue(known)
        unknown = [row for row in models if not row.get("price_known")]
        self.assertTrue(unknown)

    def test_doctor_prints_advisory_pointer(self) -> None:
        from of.model_catalog import ModelCatalog

        lines = ModelCatalog.doctor_lines()
        self.assertTrue(any("model-catalog.md" in line for line in lines))
        self.assertTrue(any("budget.tokens" in line for line in lines))
        self.assertFalse(any("of catalog" in line for line in lines))


class AdapterDetectHonesty(unittest.TestCase):
    """After mix ask, leader surfaces present/missing/PATH≠auth. Not login."""

    def test_skill_and_alias_teach_detect_honesty(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        table = skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]
        folded = table.casefold()
        detect_at = folded.index("of detect")
        self.assertLess(detect_at, folded.index("present"))
        self.assertLess(detect_at, folded.index("missing"))
        self.assertIn("path≠auth", folded)
        self.assertIn("never claim login", folded)
        alias_fold = alias.casefold()
        self.assertIn("present", alias_fold)
        self.assertIn("missing", alias_fold)
        self.assertIn("path≠auth", alias_fold)
        self.assertIn("never claim login", alias_fold)
        hero = readme[: readme.index("## Install")].casefold()
        self.assertIn("present", hero)
        self.assertIn("missing", hero)
        self.assertIn("path≠auth", hero)
        self.assertIn("login", hero)


class HardnessDetectAuthWorktree(unittest.TestCase):
    """C-015/C-016 stay Partial: detect ≠ auth; worktree is not a jail."""

    DETECT = ("credentials", "session authority")
    WORKTREE = ("honesty surface", "not a jail")
    OVERCLAIM = "already authenticated"

    @staticmethod
    def surfaces() -> dict[str, str]:
        return {
            "SKILL.md": SkillSurface.core(ROOT),
            "of/SKILL.md": SkillSurface.alias(ROOT),
            "references/skill-appendix.md": SkillSurface.appendix(ROOT),
            "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
            "docs/architecture.md": (ROOT / "docs" / "architecture.md").read_text(
                encoding="utf-8"
            ),
        }

    @staticmethod
    def folded(text: str) -> str:
        return text.casefold()

    def test_surfaces_teach_detect_not_auth(self) -> None:
        for rel, text in self.surfaces().items():
            folded = self.folded(text)
            for needle in self.DETECT:
                self.assertIn(needle, folded, f"{rel} missing {needle}")
            compact = folded.replace("-", " ")
            self.assertNotIn(self.OVERCLAIM, compact, rel)

    def test_surfaces_teach_worktree_honesty(self) -> None:
        for rel, text in self.surfaces().items():
            folded = self.folded(text)
            self.assertTrue(
                "honesty surface" in folded or "honesty surfaces" in folded,
                f"{rel} missing honesty surface",
            )
            self.assertIn("not a jail", folded, rel)
        for rel in (
            "of/SKILL.md",
            "references/skill-appendix.md",
            "README.md",
            "docs/architecture.md",
            "SLAVE.md",
        ):
            folded = self.folded((ROOT / rel).read_text(encoding="utf-8"))
            self.assertIn("security guarantee", folded, rel)

    def test_doctor_names_credentials_not_session(self) -> None:
        ops = (ROOT / "scripts" / "of" / "cli" / "ops.py").read_text(encoding="utf-8")
        self.assertIn(
            "PATH is not auth, credentials, or session authority",
            ops,
        )
        detect = (ROOT / "scripts" / "of_adapters.py").read_text(encoding="utf-8")
        self.assertIn("Not credentials or session authority", detect)

    def test_claims_matrix_keeps_partials(self) -> None:
        matrix = (ROOT / "docs" / "audit" / "claims-matrix.md").read_text(
            encoding="utf-8"
        )
        self.assertRegex(matrix, r"\| C-015 \|.*\| normal \| Partial \|")
        self.assertRegex(matrix, r"\| C-016 \|.*\| normal \| Partial \|")
        self.assertIn("credentials/session authority", matrix.casefold())
        self.assertIn("honesty surface", matrix.casefold())


class SkillFrontmatterQuoted:
    """Strict YAML-ish frontmatter load. description/compatibility must be quoted."""

    MUST_QUOTE = ("description", "compatibility")

    @staticmethod
    def block(text: str) -> str:
        if not text.startswith("---\n"):
            raise ValueError("missing opening ---")
        end = text.find("\n---\n", 4)
        if end < 0:
            raise ValueError("missing closing ---")
        return text[4:end]

    @staticmethod
    def unescape_dq(inner: str) -> str:
        out: list[str] = []
        esc = False
        for ch in inner:
            if esc:
                mapping = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
                if ch not in mapping:
                    raise ValueError(f"unknown escape \\{ch}")
                out.append(mapping[ch])
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                raise ValueError("unescaped quote in double-quoted scalar")
            else:
                out.append(ch)
        if esc:
            raise ValueError("dangling escape")
        return "".join(out)

    @classmethod
    def parse_value(cls, key: str, raw: str) -> object:
        raw = raw.strip()
        if raw == "":
            return {}
        if raw.startswith('"'):
            if len(raw) < 2 or not raw.endswith('"'):
                raise ValueError(f"{key}: unclosed double quote")
            return cls.unescape_dq(raw[1:-1])
        if key in cls.MUST_QUOTE:
            raise ValueError(f"{key} must be double-quoted")
        if ":" in raw or "—" in raw:
            raise ValueError(f"{key}: unquoted scalar contains : or em dash")
        return raw

    @classmethod
    def load(cls, text: str) -> dict:
        data: dict = {}
        nest: dict | None = None
        for line in cls.block(text).splitlines():
            if not line.strip():
                continue
            if line.startswith("  ") and nest is not None:
                if ":" not in line:
                    raise ValueError(f"bad nested line: {line}")
                key, _, rest = line.strip().partition(":")
                nest[key] = cls.parse_value(key, rest)
                continue
            nest = None
            if ":" not in line or line.startswith(" "):
                raise ValueError(f"bad line: {line}")
            key, _, rest = line.partition(":")
            val = rest.strip()
            if val == "":
                nest = {}
                data[key] = nest
                continue
            data[key] = cls.parse_value(key, rest)
        return data


class VersionedDescription(unittest.TestCase):
    def test_description_preview_starts_with_version(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f'description: "v{ver} —', skill)


class SkillFrontmatterQuotedGate(unittest.TestCase):
    """Unquoted em dash / colons skip the skill in agy. Quoted form must load."""

    def test_live_skills_strict_load(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        for rel in ("SKILL.md", "of/SKILL.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            data = SkillFrontmatterQuoted.load(text)
            self.assertIsInstance(data["description"], str, rel)
            self.assertTrue(data["description"].startswith(f"v{ver} —"), rel)
            self.assertIn("—", data["description"], rel)
            if rel == "SKILL.md":
                self.assertIn("compatibility", data)
                self.assertIsInstance(data["compatibility"], str)
                self.assertIn("3.11", data["compatibility"])
            meta = data.get("metadata")
            self.assertIsInstance(meta, dict, rel)
            self.assertEqual(meta.get("version"), ver, rel)

    def test_unquoted_emdash_colon_description_refused(self) -> None:
        bad = (
            "---\n"
            "name: orderfield\n"
            "description: v0.7.54 — Gaps as prose: of contrast --diff.\n"
            "compatibility: Requires Python 3.11+.\n"
            "---\n# body\n"
        )
        with self.assertRaises(ValueError) as ctx:
            SkillFrontmatterQuoted.load(bad)
        self.assertIn("must be double-quoted", str(ctx.exception))

    def test_quoted_colon_emdash_round_trip(self) -> None:
        good = (
            '---\n'
            'name: orderfield\n'
            'description: "v0.7.54 — Gaps as prose: of contrast --diff."\n'
            'compatibility: "Requires Python 3.11+."\n'
            'metadata:\n'
            '  version: "0.7.54"\n'
            '---\n# body\n'
        )
        data = SkillFrontmatterQuoted.load(good)
        self.assertEqual(
            data["description"], "v0.7.54 — Gaps as prose: of contrast --diff."
        )
        self.assertEqual(data["compatibility"], "Requires Python 3.11+.")
        self.assertEqual(data["metadata"]["version"], "0.7.54")


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
        self.assertIn(f'description: "v{ver} —', body)
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


class MortalInstallDemo(unittest.TestCase):
    """One-sitting wrap of install.sh + of doctor. docs/demo/mortal-install.sh."""

    SCRIPT = ROOT / "docs" / "demo" / "mortal-install.sh"

    def test_hermetic_root_doctor_ok_and_names_disk_contract(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-mortal-install-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.assertTrue(self.SCRIPT.is_file(), self.SCRIPT)
        proc = run(ROOT, "bash", str(self.SCRIPT), "--root", str(tmp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("doctor        ok", proc.stdout)
        self.assertNotIn("doctor        WARN", proc.stdout)
        self.assertNotIn("doctor        FAIL", proc.stdout)
        self.assertIn("disk contract", proc.stdout)
        self.assertIn(".orderfield/", proc.stdout)
        self.assertIn("of resume", proc.stdout)
        self.assertIn("process supervisor", proc.stdout)
        self.assertIn("of merge", proc.stdout)
        self.assertIn("mortal-install  ok", proc.stdout)
        dest = tmp / ".agents" / "skills" / "orderfield"
        self.assertTrue((dest / "SKILL.md").is_file(), proc.stdout)
        self.assertTrue((dest / "scripts" / "of.py").is_file())
        link = tmp / ".local" / "bin" / "of"
        self.assertTrue(link.is_symlink(), proc.stdout)
        self.assertEqual(link.resolve(), (dest / "scripts" / "of.py").resolve())

    def test_refuses_without_explicit_target(self) -> None:
        proc = run(ROOT, "bash", str(self.SCRIPT))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("--root", proc.stderr)
        self.assertIn("--global", proc.stderr)

    def test_refuses_detached_script_without_tree(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-mortal-lone-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        lone = tmp / "mortal-install.sh"
        lone.write_text(self.SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        proc = run(tmp, "bash", str(lone), "--root", str(tmp / "dest"))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("extracted release tree", proc.stderr)
        self.assertIn("PUBLISH.md", proc.stderr)


class SkillRespawnInFlight(unittest.TestCase):
    """SKILL teaches leftover residual does not hide a started-only re-spawn."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_leftover_residual(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("leftover residual", table)
        self.assertIn("started-only", table)
        self.assertIn("re-spawn", table)
        alias_fold = alias.casefold()
        self.assertIn("leftover residual", alias_fold)
        self.assertIn("started-only", alias_fold)
        self.assertIn("re-spawn", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("leftover residual", appendix_fold)
        self.assertIn("started-only", appendix_fold)
        self.assertIn("re-spawn", appendix_fold)


class SkillEmptyWavePhase(unittest.TestCase):
    """SKILL teaches empty-wave of phase without --force. #166."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_empty_wave_phase(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("empty current wave", table)
        self.assertIn("of phase", table)
        self.assertIn("nothing to integrate", table)
        self.assertIn("do not `--force`", table)
        self.assertIn("packets still require integrate", table)
        alias_fold = alias.casefold()
        self.assertIn("empty current wave", alias_fold)
        self.assertIn("nothing to integrate", alias_fold)
        self.assertIn("without `--force`", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("packed_children", appendix_fold)
        self.assertIn("nothing to integrate", appendix_fold)
        self.assertIn("do not `--force`", appendix_fold)
        self.assertIn("skip-cut", appendix_fold)


class SkillResumeRecompute(unittest.TestCase):
    """SKILL teaches resume INTEGRATE --RECOMPUTE when the report digest drifted."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_resume_recompute(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("integrate --recompute", table)
        self.assertIn("digest drifted", table)
        self.assertIn("do not next-wave", table)
        alias_fold = alias.casefold()
        self.assertIn("integrate --recompute", alias_fold)
        self.assertIn("digest drifted", alias_fold)
        self.assertIn("do not next-wave", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("integrate --recompute", appendix_fold)
        self.assertIn("integrationdigest", appendix_fold)
        self.assertIn("session_id", appendix_fold)
        source = (ROOT / "scripts" / "of" / "regime.py").read_text(encoding="utf-8")
        self.assertIn("class IntegrationDigest:", source)


class SkillAuditPressure(unittest.TestCase):
    """SKILL teaches gc / shrink before close when audit is OVER."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_gc_before_close(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("audit over", table)
        self.assertIn("of gc --audit", table)
        self.assertIn("before", table)
        self.assertIn("of close", table)
        self.assertIn("not fail", table)
        self.assertIn("not a close gate", table)
        alias_fold = alias.casefold()
        self.assertIn("audit", alias_fold)
        self.assertIn("over", alias_fold)
        self.assertIn("of gc --audit", alias_fold)
        self.assertIn("before close", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("auditpressure", appendix_fold)
        self.assertIn("of gc --audit", appendix_fold)
        self.assertIn("before close", appendix_fold)
        source = (ROOT / "scripts" / "of" / "retain.py").read_text(encoding="utf-8")
        self.assertIn("class AuditPressure:", source)


class SkillPlanDocSync(unittest.TestCase):
    """SKILL teaches Mode A patch vs Mode B dump+ask for cited plan docs."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_modes_and_findings(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("docs/plans", table)
        self.assertIn("mode a", table)
        self.assertIn("mode b", table)
        self.assertIn("docs_sync.md", table)
        self.assertIn("ask", table)
        self.assertIn("plandocsync", table)
        self.assertIn("not a close gate", table)
        self.assertIn("project finding", table)
        alias_fold = alias.casefold()
        self.assertIn("docs/plans", alias_fold)
        self.assertIn("mode a", alias_fold)
        self.assertIn("mode b", alias_fold)
        self.assertIn("docs_sync.md", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("plandocsync", appendix_fold)
        self.assertIn("mode a", appendix_fold)
        self.assertIn("mode b", appendix_fold)
        self.assertIn("docs_sync.md", appendix_fold)
        self.assertIn("project finding", appendix_fold)
        source = (ROOT / "scripts" / "of" / "regime.py").read_text(encoding="utf-8")
        self.assertIn("class PlanDocSync:", source)


class SkillCollectNextIntegrate(unittest.TestCase):
    """After successful collect, printed next is INTEGRATE. #204."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_integrate_after_collect(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("resume next `integrate`", table)
        self.assertIn("do not collect again", table)
        self.assertIn("collectready", table)
        self.assertIn("invalid=0", table)
        alias_fold = alias.casefold()
        self.assertIn("next is integrate", alias_fold)
        self.assertIn("not collect", alias_fold)
        self.assertIn("do not collect again", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("next=integrate", appendix_fold)
        self.assertIn("do not collect again", appendix_fold)
        self.assertIn("collectready", appendix_fold)
        source = (ROOT / "scripts" / "of" / "field.py").read_text(encoding="utf-8")
        self.assertIn("class CollectReady:", source)
        self.assertIn("ACTION = \"integrate\"", source)


class SkillDriveAfterIntegrate(unittest.TestCase):
    """After integrate, execute next same turn. Report is not a stop. #191."""

    SPEAK = "report is not a stop"
    WAIT = "do not wait for ok/pulse"
    CONSENT = "not a consent ask"

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_agents_teach_drive_not_consent_bleed(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        table = self.table(core).casefold()
        self.assertIn("collect+integrate", table)
        self.assertIn(self.SPEAK, table)
        self.assertIn(self.WAIT, table)
        self.assertIn(self.CONSENT, table)
        self.assertIn("not after ordinary integrate", table)
        self.assertIn("fresh-context review packet", table)
        self.assertIn("must ask", table)
        core_fold = core.casefold()
        self.assertIn("not invent a consent ask", core_fold)
        self.assertIn("ordinary next-wave/pack is not the adversary", core_fold)
        alias_fold = alias.casefold()
        self.assertIn(self.SPEAK, alias_fold)
        self.assertIn(self.WAIT, alias_fold)
        self.assertIn("not a consent ask", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn(self.SPEAK, appendix_fold)
        self.assertIn("driveafterintegrate", appendix_fold)
        self.assertIn("not invent a consent ask", appendix_fold)
        self.assertIn("ordinary next-wave/pack is not the adversary", appendix_fold)
        self.assertIn("recovery/drive-after-integrate", appendix_fold)
        agents_fold = agents.casefold()
        self.assertIn(self.SPEAK, agents_fold)
        self.assertIn(self.WAIT, agents_fold)
        self.assertIn("not invent a consent ask", agents_fold)
        source = (ROOT / "scripts" / "of" / "cli" / "ops.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class DriveAfterIntegrate:", source)
        self.assertIn("report is not a stop", source)

    def test_consent_gates_still_ask(self) -> None:
        core = SkillSurface.core(ROOT)
        table = self.table(core).casefold()
        self.assertIn("after wave, before close", table)
        self.assertLess(table.index("must ask"), table.index("of close --checklist"))
        self.assertIn("same-harness", table)
        self.assertIn("must ask", table)
        self.assertIn("must propose", table)


class SkillCheckoutAutoContinueHonesty(unittest.TestCase):
    """Clone/checkout of an open field still auto-continues. Rule 0 stays."""

    RISK = "operator risk"
    ESCAPE = "not an escape"
    CLONE = "clone/checkout"
    DEST = "home dest"
    RULE0 = (
        "Only explicit user pause/stop/cancel (`pause`, `stop`, "
        "`wait on the field`, `cancel the mission`, `of init --force`) "
        "or `spec_closed` ends auto-continue."
    )
    FORBIDDEN = (
        "OF_NO_AUTO_CONTINUE",
        "checkout mode",
        "auto_continue=off",
    )

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    @staticmethod
    def surfaces() -> dict[str, str]:
        return {
            "SKILL.md": SkillSurface.core(ROOT),
            "of/SKILL.md": SkillSurface.alias(ROOT),
            "references/skill-appendix.md": SkillSurface.appendix(ROOT),
            "AGENTS.md": (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
            "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
            "docs/external-brief.md": (ROOT / "docs" / "external-brief.md").read_text(
                encoding="utf-8"
            ),
            "docs/troubleshooting.md": (
                ROOT / "docs" / "troubleshooting.md"
            ).read_text(encoding="utf-8"),
        }

    def test_rule_0_stays(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(self.RULE0, agents)
        self.assertIn("Open field auto-continues.", agents)

    def test_surfaces_teach_checkout_risk_not_escape(self) -> None:
        for rel, text in self.surfaces().items():
            folded = text.casefold()
            self.assertIn(self.RISK, folded, rel)
            self.assertTrue(
                self.ESCAPE in folded or "not a silent escape" in folded,
                f"{rel} missing not-an-escape",
            )
            self.assertTrue(
                self.CLONE in folded or "cloning" in folded or "clone or checkout" in folded,
                f"{rel} missing clone/checkout",
            )
            if rel == "docs/troubleshooting.md":
                self.assertIn("not invent", folded, rel)
                continue
            compact = folded.replace("-", " ").replace("_", " ")
            for banned in self.FORBIDDEN:
                self.assertNotIn(
                    banned.casefold().replace("-", " ").replace("_", " "),
                    compact,
                    rel,
                )

    def test_core_table_and_dests_pair(self) -> None:
        core = SkillSurface.core(ROOT)
        table = self.table(core).casefold()
        self.assertIn("clone/checkout", table)
        self.assertIn(self.RISK, table)
        self.assertIn(self.ESCAPE, table)
        self.assertIn("of resume", table)
        alias = SkillSurface.alias(ROOT).casefold()
        appendix = SkillSurface.appendix(ROOT).casefold()
        readme = (ROOT / "README.md").read_text(encoding="utf-8").casefold()
        for rel, text in (
            ("of/SKILL.md", alias),
            ("references/skill-appendix.md", appendix),
            ("README.md", readme),
        ):
            self.assertIn(self.DEST, text, rel)
            self.assertIn("~/.agents", text, rel)
            self.assertIn("~/.claude", text, rel)
            self.assertIn("~/.cursor", text, rel)

    def test_kernel_has_no_silent_skip(self) -> None:
        ops = (ROOT / "scripts" / "of" / "cli" / "ops.py").read_text(encoding="utf-8")
        self.assertNotIn("OF_NO_AUTO_CONTINUE", ops)
        self.assertIn("resume_auto_continue_lines", ops)
        self.assertIn("class DriveAfterIntegrate:", ops)

    def test_claims_matrix_keeps_rule_0(self) -> None:
        matrix = (ROOT / "docs" / "audit" / "claims-matrix.md").read_text(
            encoding="utf-8"
        )
        self.assertRegex(matrix, r"\| C-025 \|.*\| normal \| OK \|")
        self.assertIn("SkillCheckoutAutoContinueHonesty", matrix)
        self.assertIn("operator risk, not an escape", matrix.casefold())


class SkillRevStaleUnpack(unittest.TestCase):
    """SKILL teaches rev-stale dead child → UNPACK --FORCE, not spawn."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_rev_stale_unpack(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("unpack --force", table)
        self.assertIn("do not spawn", table)
        self.assertIn("order.rev", table)
        alias_fold = alias.casefold()
        self.assertIn("unpack --force", alias_fold)
        self.assertIn("do not spawn", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("unpack --force", appendix_fold)
        self.assertIn("packetrevstale", appendix_fold)
        self.assertIn("do not spawn", appendix_fold)
        source = (ROOT / "scripts" / "of" / "pack.py").read_text(encoding="utf-8")
        self.assertIn("class PacketRevStale:", source)


class SkillPostCloseTerminal(unittest.TestCase):
    """SKILL teaches successful close is terminal. #180."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_post_close_terminal(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("successful close", table)
        self.assertIn("not active", table)
        self.assertIn("not alive", table)
        self.assertIn("spawn_blocked", table)
        self.assertIn("recovery/post-close-terminal", table)
        alias_fold = alias.casefold()
        self.assertIn("not active", alias_fold)
        self.assertIn("not alive", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("not a live spawn surface", appendix_fold)
        self.assertIn("spawn_blocked", appendix_fold)
        self.assertIn("recovery/post-close-terminal", appendix_fold)


class SkillPhaseNextWave(unittest.TestCase):
    """SKILL teaches of phase then next-wave without recomputing the prior wave."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_phase_then_next_wave(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("after successful `of phase`", table)
        self.assertIn("of next-wave", table)
        self.assertIn("do not `--recompute`", table)
        alias_fold = alias.casefold()
        self.assertIn("of phase", alias_fold)
        self.assertIn("of next-wave", alias_fold)
        self.assertIn("do not integrate `--recompute`", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("phasedigest", appendix_fold)
        self.assertIn("of next-wave", appendix_fold)
        self.assertIn("do not", appendix_fold)
        self.assertIn("integrate --recompute", appendix_fold)
        source = (ROOT / "scripts" / "of" / "regime.py").read_text(encoding="utf-8")
        self.assertIn("class PhaseDigest:", source)


class SkillPackedOnlyStatus(unittest.TestCase):
    """SKILL teaches PACKED / SPAWN. Packed-only is not ALIVE."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_packed_and_spawn(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("packed", table)
        self.assertIn("next spawn", table)
        self.assertIn("spawn metadata", table)
        self.assertIn("do not hold as if alive", table)
        alias_fold = alias.casefold()
        self.assertIn("packed", alias_fold)
        self.assertIn("spawned 0", alias_fold)
        self.assertIn("next spawn", alias_fold)
        self.assertIn("PACKED", appendix)
        self.assertIn("SPAWN", appendix)
        self.assertIn("no spawn record", appendix)


class SkillProductionMode(unittest.TestCase):
    """SKILL teaches production-mode invariants + Gate A before features."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_gate_a_before_features(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("production mission", table)
        self.assertIn("gate a", table)
        self.assertIn("before features", table)
        self.assertIn("--role implementer", table)
        self.assertIn("runtime_ownership", table)
        self.assertIn("of merge", table)
        self.assertNotIn("of merge --", table)
        alias_fold = alias.casefold()
        self.assertIn("production mode", alias_fold)
        self.assertIn("gate a", alias_fold)
        self.assertIn("--role implementer", alias_fold)
        self.assertIn("runtime_ownership", alias_fold)
        self.assertIn("of merge", alias_fold)
        self.assertNotIn("of merge --", alias)
        appendix_fold = appendix.casefold()
        self.assertIn("#### production mode", appendix_fold)
        self.assertIn("**gate a before features.**", appendix_fold)
        self.assertIn("--role implementer", appendix_fold)
        self.assertIn("runtime_ownership", appendix_fold)
        self.assertIn("never invent a **sí**", appendix_fold)
        self.assertIn("of pack --owns-requirement", appendix_fold)
        self.assertIn("no `of gate`", appendix_fold)
        self.assertNotIn("of merge --", appendix)
        self.assertIn("#### Production mode", appendix)
        self.assertIn("**Gate A before features.**", appendix)
        self.assertEqual(SkillRunbookPath.errors(ROOT), [])
        for text, rel in (
            (self.table(core), "SKILL.md table"),
            (alias, "of/SKILL.md"),
            (appendix, "references/skill-appendix.md"),
        ):
            errs = SkillRunbookPath.mention_errors(text, rel)
            self.assertEqual(errs, [], errs)

    def test_captions_only_prod15_fails(self) -> None:
        fake = "production mode day-90 ops are important; write docs later"
        errs = SkillRunbookPath.mention_errors(fake, "fake.md")
        self.assertTrue(any(SkillRunbookPath.ROW in e for e in errs), errs)
        self.assertTrue(any(SkillRunbookPath.RUNBOOK in e for e in errs), errs)
        self.assertTrue(any(SkillRunbookPath.DONE_WHEN in e for e in errs), errs)
        self.assertTrue(any(SkillRunbookPath.REFUSE in e for e in errs), errs)


class SkillWebhookReplayPair(unittest.TestCase):
    """SKILL teaches webhook signature + replay is a contrast PAIR gate."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_webhook_pair(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("webhook", table)
        self.assertIn("replay", table)
        self.assertIn("hmac", table)
        self.assertIn("--both-sides", table)
        self.assertIn("pair", table)
        alias_fold = alias.casefold()
        self.assertIn("webhook", alias_fold)
        self.assertIn("replay", alias_fold)
        self.assertIn("--both-sides", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("webhook", appendix_fold)
        self.assertIn("hmac", appendix_fold)
        self.assertIn("replay", appendix_fold)
        self.assertIn("--both-sides", appendix_fold)
        self.assertIn("webhookpair", appendix_fold.replace(" ", ""))


class LivingMapGate(unittest.TestCase):
    """Living map names checklist → of contrast / of close / residual."""

    def test_pages_name_verbs_not_captions(self) -> None:
        self.assertEqual(LivingMap.errors(ROOT), [])

    def test_captions_only_page_fails(self) -> None:
        text = "close checklist captions only; no mapped verbs"
        errs = LivingMap.page_errors(text, "fake.md")
        self.assertTrue(
            any(LivingMap.BINDING in e for e in errs),
            errs,
        )
        self.assertTrue(any("of close" in e for e in errs), errs)
        self.assertTrue(any("residual" in e for e in errs), errs)
        self.assertTrue(any(LivingMap.NO_SECOND in e for e in errs), errs)

    def test_captions_only_prod15_teaching_fails(self) -> None:
        fake = "production checklist captions; day-90 ops later"
        errs = SkillRunbookPath.mention_errors(fake, "fake.md")
        self.assertTrue(any("prod§15" in e for e in errs), errs)
        self.assertTrue(any("runbook" in e for e in errs), errs)
        self.assertTrue(any("done_when" in e for e in errs), errs)
        self.assertTrue(any("close refuse" in e for e in errs), errs)

    def test_mix_captions_without_verbs_fail(self) -> None:
        text = "multi-harness mix is powerful; use many CLIs"
        errs = SkillHarnessMix.mention_errors(text, "fake.md")
        self.assertTrue(any("of pack" in e for e in errs), errs)
        self.assertTrue(any("of doctor" in e for e in errs), errs)
        self.assertTrue(any("of detect" in e for e in errs), errs)
        self.assertTrue(any("must ask" in e for e in errs), errs)

    def test_script_exits_ok_on_checkout(self) -> None:
        proc = run(ROOT, sys.executable, str(ROOT / "scripts" / "living_map.py"), str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OK living map", proc.stdout)


class SkillLivingMap(unittest.TestCase):
    """SKILL / /of / appendix teach checklist → contrast / close / residual."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_living_map(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn(LivingMap.BINDING, table)
        self.assertIn("of close --checklist", table)
        self.assertIn("residual", table)
        self.assertIn(LivingMap.NO_SECOND, table)
        self.assertIn("closeevidence", table.replace(" ", "").replace("`", ""))
        alias_fold = alias.casefold()
        self.assertIn(LivingMap.BINDING, alias_fold)
        self.assertIn("of close", alias_fold)
        self.assertIn("residual", alias_fold)
        self.assertIn(LivingMap.NO_SECOND, alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn(LivingMap.BINDING, appendix_fold)
        self.assertIn("#### production mode", appendix_fold)
        self.assertIn("contractsurface", appendix_fold.replace(" ", ""))
        self.assertIn("closeevidence", appendix_fold.replace(" ", ""))
        self.assertIn("of close --checklist", appendix_fold)
        self.assertIn(LivingMap.NO_SECOND, appendix_fold)
        self.assertIn("prod§15", appendix_fold)
        self.assertIn("runbook", appendix_fold)
        self.assertIn("done_when", appendix_fold)


class SkillHarnessMixPlaybook(unittest.TestCase):
    """SKILL teaches when to mix vs roles-on-one; captions-only mix fails."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_bind_mix_to_verbs(self) -> None:
        self.assertEqual(SkillHarnessMix.errors(ROOT), [])
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn(SkillHarnessMix.MIX, table)
        self.assertIn(SkillHarnessMix.WHEN, table)
        self.assertIn("of doctor", table)
        self.assertIn("of detect", table)
        self.assertIn("of pack", table)
        self.assertIn("of spawn", table)
        self.assertIn("of collect", table)
        self.assertIn("of contrast", table)
        self.assertIn("of close", table)
        alias_fold = alias.casefold()
        self.assertIn(SkillHarnessMix.MIX, alias_fold)
        self.assertIn(SkillHarnessMix.WHEN, alias_fold)
        self.assertIn("of collect", alias_fold)
        self.assertIn("of doctor", alias_fold)
        self.assertIn(SkillHarnessMix.HEADING, appendix)
        section = SkillHarnessMix.playbook_section(appendix)
        self.assertIsNotNone(section)
        folded = section.casefold()
        self.assertIn(SkillHarnessMix.WHEN, folded)
        for name in SkillHarnessMix.HARNESSES:
            self.assertIn(name, folded)
        for verb in SkillHarnessMix.VERBS:
            self.assertIn(verb, folded)

    def test_captions_only_mix_playbook_fails(self) -> None:
        fake = "#### Multi-harness mix\n\nUse many CLIs. multi-harness mix is great.\n"
        errs = SkillHarnessMix.playbook_errors(fake, "fake.md")
        self.assertTrue(any("of pack" in e for e in errs), errs)
        self.assertTrue(any("of doctor" in e for e in errs), errs)
        self.assertTrue(any(SkillHarnessMix.WHEN in e for e in errs), errs)
        self.assertTrue(any("claude" in e for e in errs), errs)


class SkillEfficiencyMixPlaybook(unittest.TestCase):
    """SKILL teaches mid-mission mix from honest signals; unknown if none."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_unknown_balance(self) -> None:
        self.assertEqual(SkillEfficiencyMix.errors(ROOT), [])
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn(SkillEfficiencyMix.UNKNOWN, table)
        self.assertIn(SkillEfficiencyMix.NEVER_INVENT, table)
        self.assertIn(SkillEfficiencyMix.RESERVED, table)
        self.assertIn("of doctor", table)
        self.assertIn("efficiency", table)
        self.assertIn("must ask", table)
        alias_fold = alias.casefold()
        self.assertIn(SkillEfficiencyMix.UNKNOWN, alias_fold)
        self.assertIn(SkillEfficiencyMix.NEVER_INVENT, alias_fold)
        self.assertIn(SkillEfficiencyMix.RESERVED, alias_fold)
        self.assertIn(SkillEfficiencyMix.HEADING, appendix)
        appendix_fold = appendix.casefold()
        self.assertIn("adapterbalance", appendix_fold.replace(" ", "").replace("`", ""))
        self.assertIn("statusline", appendix_fold.replace(" ", ""))

    def test_missing_unknown_fails(self) -> None:
        fake = "rebalance to frontier now; spend is 80k tokens"
        errs = SkillEfficiencyMix.mention_errors(fake, "fake.md")
        self.assertTrue(any(SkillEfficiencyMix.UNKNOWN in e for e in errs), errs)
        self.assertTrue(any(SkillEfficiencyMix.NEVER_INVENT in e for e in errs), errs)
        self.assertTrue(any(SkillEfficiencyMix.RESERVED in e for e in errs), errs)


class SkillCloseEvidence(unittest.TestCase):
    """SKILL teaches done residual close evidence: artifact SHA + rollback."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_close_evidence(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("artifact_sha", table)
        self.assertIn("rollback", table)
        self.assertIn("closeevidence", table.replace(" ", "").replace("`", ""))
        alias_fold = alias.casefold()
        self.assertIn("artifact_sha", alias_fold)
        self.assertIn("rollback", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("artifact_sha", appendix_fold)
        self.assertIn("rollback:", appendix_fold)
        self.assertIn("closeevidence", appendix_fold.replace(" ", ""))


class SkillContractSurface(unittest.TestCase):
    """SKILL teaches timeout / idempotency / health / version as VERIFIED_CONTRACT."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_contract_surface(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("timeout", table)
        self.assertIn("idempoten", table)
        self.assertIn("health", table)
        self.assertIn("/version", table)
        self.assertIn("release header", table)
        self.assertIn("verified_contract", table)
        self.assertIn("contractsurface", table.replace(" ", "").replace("`", ""))
        alias_fold = alias.casefold()
        self.assertIn("timeout", alias_fold)
        self.assertIn("idempoten", alias_fold)
        self.assertIn("health", alias_fold)
        self.assertIn("/version", alias_fold)
        self.assertIn("release header", alias_fold)
        self.assertIn("verified_contract", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("timeout", appendix_fold)
        self.assertIn("idempoten", appendix_fold)
        self.assertIn("/health", appendix_fold)
        self.assertIn("/version", appendix_fold)
        self.assertIn("release header", appendix_fold)
        self.assertIn("verified_contract", appendix_fold)
        self.assertIn("contractsurface", appendix_fold.replace(" ", ""))


class SkillLearnLengthAdvisory(unittest.TestCase):
    """SKILL teaches of learn length is advisory like pack --slice."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_learn_advisory(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("of learn", table)
        self.assertIn("advisory", table)
        self.assertIn("do not refuse", table)
        self.assertIn("work/scratch/leader", table)
        alias_fold = alias.casefold()
        self.assertIn("of learn", alias_fold)
        self.assertIn("advisory", alias_fold)
        self.assertIn("work/scratch/leader", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("of learn", appendix_fold)
        self.assertIn("advisory", appendix_fold)
        self.assertIn("do not refuse", appendix_fold)
        self.assertIn("work/scratch/leader", appendix_fold)
        self.assertIn("learning.lines", appendix)


class SkillDoctorClosedHistorical(unittest.TestCase):
    """SKILL teaches closed-field historical packs are informational."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_closed_historical(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("of doctor", table)
        self.assertIn("closed-field historical", table)
        self.assertIn("informational", table)
        self.assertIn("not fail", table)
        self.assertIn("do not rewrite a closed audit trail", table)
        alias_fold = alias.casefold()
        self.assertIn("closed-field historical", alias_fold)
        self.assertIn("informational", alias_fold)
        self.assertIn("not fail", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("closed-field historical", appendix_fold)
        self.assertIn("informational", appendix_fold)


class SkillDoctorOpenHygiene(unittest.TestCase):
    """SKILL teaches leftover root migrate-required and open-sibling CLOSE."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_name_migrate_and_open_siblings(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("of doctor", table)
        self.assertIn("leftover root", table)
        self.assertIn("of migrate", table)
        self.assertIn("sibling fields without close", table)
        self.assertIn("hygiene", table)
        self.assertIn("warn", table)
        alias_fold = alias.casefold()
        self.assertIn("leftover root", alias_fold)
        self.assertIn("of migrate", alias_fold)
        self.assertIn("sibling fields without close", alias_fold)
        self.assertIn("hygiene", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("leftover root", appendix_fold)
        self.assertIn("migrate required", appendix_fold)
        self.assertIn("of migrate", appendix_fold)
        self.assertIn("sibling fields without close", appendix_fold)
        self.assertIn("hygiene", appendix_fold)
        self.assertIn("warn", appendix_fold)


class SkillCollectConservativeDiagnostic(unittest.TestCase):
    """Missing residual diagnostics report facts, not universal inability."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_pending_and_possible_permissions(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        for text in (self.table(core), alias, appendix):
            folded = text.casefold()
            self.assertIn("pending/unavailable", folded)
            self.assertIn("adapter", folded)
            self.assertIn("outcome", folded)
            self.assertIn("denied_actions", folded)
            self.assertIn("permissions may be involved", folded)
            self.assertIn("possibility, not proof", folded)
            self.assertIn("conservative children may still write", folded)


class SkillPartialIntegrateInFlight(unittest.TestCase):
    """Appendix teaches --partial hold names in-flight siblings."""

    def test_appendix_names_landed_complete_not_wave_closed(self) -> None:
        appendix = SkillSurface.appendix(ROOT).casefold()
        self.assertIn("integrate --wave n --partial", appendix)
        self.assertIn("skipped_in_flight", appendix)
        self.assertIn("landed residuals are complete", appendix)
        self.assertIn("siblings still in flight", appendix)
        self.assertIn("wave closed", appendix)
        self.assertIn("complete-wave", appendix)
        self.assertIn("recovery/partial-integrate-in-flight", appendix)


class SkillAntiDoneTheater(unittest.TestCase):
    """Claim shipped requires contrast + residual empty + quoted speak.

    Reuse (design-first; written before the wording cut):

    | Existing | Already covers | This cut |
    |---|---|---|
    | `CloseChecklist.speak_line` (0.7.68) | prints SPEAK on `--checklist` | Skill must quote that line |
    | `SkillAntiDoneTheater` | contrast RESOLVED + residual empty | speak-quote duty on core/alias/appendix |
    | `CloseChecklistProof` | SPEAK on checklist stdout | stays |
    | `InFlightSignal.speak_line` | quote-PULSE while flying | pair; do not fork |
    | Prod§21 living map | checklist → contrast / close / residual | ship row names quote speak |

    Net-new surface: none. Protocol, not a kernel chat parser. The
    evaluator `speak` row is a different line — quote CloseChecklist.SPEAK.
    """

    QUOTE = "quote the printed `speak` line"
    SPEAK = "do not claim shipped unless contrast RESOLVED and residual empty"

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    @staticmethod
    def speak_quote_errors(text: str, rel: str) -> list[str]:
        """Refuse pages that print speak without requiring the quote."""
        errors: list[str] = []
        folded = text.casefold()
        if SkillAntiDoneTheater.QUOTE.casefold() not in folded:
            errors.append(f"{rel} missing {SkillAntiDoneTheater.QUOTE!r}")
        if SkillAntiDoneTheater.SPEAK not in text:
            errors.append(f"{rel} missing {SkillAntiDoneTheater.SPEAK!r}")
        if "that `speak` line is not quoted" not in text:
            errors.append(f"{rel} missing refuse unless speak quoted")
        return errors

    def test_core_and_alias_refuse_shipped_without_disk_facts(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core)
        table_fold = table.casefold()
        self.assertIn("claim shipped", table_fold)
        self.assertIn("of contrast", table_fold)
        self.assertIn("of close --checklist", table_fold)
        self.assertIn("residual empty", table_fold)
        self.assertIn("mechanical", table_fold)
        self.assertIn("not your judgment", table_fold)
        self.assertIn("quote-pulse", table_fold)
        self.assertIn("Anti-done-theater", core)
        self.assertIn("mechanical", core.casefold())
        alias_fold = alias.casefold()
        self.assertIn("claim shipped", alias_fold)
        self.assertIn("of contrast", alias_fold)
        self.assertIn("of close --checklist", alias_fold)
        self.assertIn("mechanical", alias_fold)
        self.assertIn(self.SPEAK, appendix)
        self.assertIn("mechanical", appendix.casefold())
        self.assertIn("not your judgment", appendix.casefold())
        self.assertEqual(self.speak_quote_errors(table, "SKILL.md table"), [])
        self.assertEqual(self.speak_quote_errors(alias, "of/SKILL.md"), [])
        self.assertEqual(
            self.speak_quote_errors(appendix, "references/skill-appendix.md"),
            [],
        )
        self.assertIn(self.QUOTE, core)
        self.assertIn(self.SPEAK, core)

    def test_prints_speak_without_quote_duty_fails(self) -> None:
        text = (
            "run of contrast and of close --checklist. "
            "quote contrast RESOLVED and residual empty. "
            "Checklist prints speak. Mechanical, not your judgment."
        )
        errs = self.speak_quote_errors(text, "fake.md")
        self.assertTrue(
            any(self.QUOTE in e for e in errs),
            errs,
        )
        self.assertTrue(
            any(self.SPEAK in e for e in errs),
            errs,
        )


class SkillOrcaWorkerTeardown(unittest.TestCase):
    """Orca worker-start must pair stop/release. Not a process supervisor."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_adapters_teach_stop_release(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        adapters = (ROOT / "references" / "adapters.md").read_text(encoding="utf-8")
        slave = (ROOT / "SLAVE.md").read_text(encoding="utf-8")
        table = self.table(core).casefold()
        self.assertIn("worker-start", table)
        self.assertIn("worker-stop", table)
        self.assertIn("worker-release", table)
        self.assertIn("of worktree remove", table)
        self.assertIn("not a supervisor", table)
        stop_at = table.index("worker-stop")
        release_at = table.index("worker-release")
        self.assertLess(stop_at, release_at)
        alias_fold = alias.casefold()
        self.assertIn("worker-stop", alias_fold)
        self.assertIn("worker-release", alias_fold)
        self.assertIn("of worktree remove", alias_fold)
        self.assertIn("not a process supervisor", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("worker-start", appendix_fold)
        self.assertIn("worker-stop", appendix_fold)
        self.assertIn("worker-release", appendix_fold)
        self.assertIn("never leave `terminal=retained`", appendix_fold)
        self.assertIn("of worktree remove", appendix_fold)
        self.assertIn("not a process supervisor", appendix_fold)
        adapters_fold = adapters.casefold()
        self.assertIn("start↔stop/release", adapters)
        self.assertIn("worker-stop --dispatch", adapters_fold)
        self.assertIn("worker-release --dispatch", adapters_fold)
        self.assertIn("worker-retain", adapters_fold)
        self.assertIn("worker-list", adapters_fold)
        self.assertIn("does not delete worktrees", adapters_fold)
        self.assertIn("does not poll orca", adapters_fold)
        self.assertIn("not a process supervisor", adapters_fold)
        slave_fold = slave.casefold()
        self.assertIn("remove the worktree when the slice closes", slave_fold)
        self.assertIn("stops and releases orca workers", slave_fold)
        self.assertIn("does not delete this worktree", slave_fold)

    def test_teaching_is_not_a_kernel_process_manager(self) -> None:
        adapters = (ROOT / "scripts" / "of_adapters.py").read_text(encoding="utf-8")
        self.assertIn("task-create", adapters)
        self.assertNotIn("worker-stop", adapters)
        self.assertNotIn("worker-release", adapters)
        self.assertNotIn("worker-start", adapters)


class SkillGenericAgentArgv(unittest.TestCase):
    """Core, alias, appendix, and adapter docs teach OF_AGENT shlex argv."""

    def test_all_skill_surfaces_name_shlex_and_space_path(self) -> None:
        surfaces = {
            "SKILL.md": SkillSurface.core(ROOT),
            "of/SKILL.md": SkillSurface.alias(ROOT),
            "references/skill-appendix.md": SkillSurface.appendix(ROOT),
            "references/adapters.md": (
                ROOT / "references" / "adapters.md"
            ).read_text(encoding="utf-8"),
        }
        for rel, text in surfaces.items():
            folded = text.casefold()
            with self.subTest(rel=rel):
                self.assertIn("of_agent", folded)
                self.assertIn("shlex", folded)
                self.assertIn("spaces", folded)
                self.assertIn("dry-run", folded)
                self.assertTrue(
                    "shlex.join" in folded or "shlex.join" in text,
                    rel,
                )

    def test_kernel_uses_static_generic_agent_class(self) -> None:
        source = (ROOT / "scripts" / "of_adapters.py").read_text(encoding="utf-8")
        self.assertIn("class GenericAgent:", source)
        self.assertIn("shlex.split", source)
        field = (ROOT / "scripts" / "of" / "field.py").read_text(encoding="utf-8")
        self.assertIn("shlex.join", field)


class SkillCodexWorktreeSpawn(unittest.TestCase):
    """Core, alias, appendix, and adapter docs teach the shipped Codex roots."""

    def test_all_skill_surfaces_name_worktree_roots_and_refusal(self) -> None:
        surfaces = {
            "SKILL.md": SkillSurface.core(ROOT),
            "of/SKILL.md": SkillSurface.alias(ROOT),
            "references/skill-appendix.md": SkillSurface.appendix(ROOT),
            "references/adapters.md": (
                ROOT / "references" / "adapters.md"
            ).read_text(encoding="utf-8"),
        }
        for rel, text in surfaces.items():
            folded = text.casefold()
            with self.subTest(rel=rel):
                self.assertIn("-c <", folded)
                self.assertIn("worktree>", folded)
                self.assertIn("--add-dir", folded)
                self.assertIn("field", folded)
                self.assertTrue(
                    "git common" in folded or "git-common-dir" in folded,
                    rel,
                )
                self.assertIn("refus", folded)
                self.assertIn("before launch", folded)

    def test_kernel_uses_static_codex_worktree_argv_class(self) -> None:
        source = (ROOT / "scripts" / "of_adapters.py").read_text(encoding="utf-8")
        self.assertIn("class CodexWorktree:", source)
        self.assertIn('"-C"', source)
        self.assertIn('"--add-dir"', source)
        self.assertIn('"--git-common-dir"', source)


class SkillEvaluatorPacket(unittest.TestCase):
    """After a wave, ask consent for a fresh-context review packet before close."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_ask_before_close(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        ask_at = table.index("ask")
        close_at = table.index("of close")
        self.assertLess(ask_at, close_at)
        self.assertIn("fresh-context review packet", table)
        self.assertIn("never silent", table)
        self.assertIn("--role adversary", table)
        self.assertIn("--role verifier", table)
        self.assertIn("self-praise", table)
        self.assertIn("not a new close gate", table)
        alias_fold = alias.casefold()
        self.assertIn("fresh-context review packet", alias_fold)
        self.assertIn("never silent", alias_fold)
        self.assertIn("adversary", alias_fold)
        self.assertIn("verifier", alias_fold)
        self.assertIn("must ask", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("fresh-context review packet", appendix_fold)
        self.assertIn("never silent", appendix_fold)
        self.assertIn("self-praise is not review", appendix_fold)
        self.assertIn("not a new close gate", appendix_fold)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        hero = readme[: readme.index("## Install")].casefold()
        self.assertIn("fresh-context review packet", hero)
        self.assertIn("never silent", hero)


class SkillSpawnEndedSignal(unittest.TestCase):
    """SKILL teaches done_without_residual and host Write ≠ escalate_up. #200."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_ended_spawn_signal(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("done_without_residual", table)
        self.assertIn("not a healthy", table)
        self.assertIn("alive", table)
        self.assertIn("denied_actions", table)
        self.assertIn("write", table)
        self.assertIn("escalate_up", table)
        for body, name in (
            (core, "SKILL.md"),
            (alias, "of/SKILL.md"),
            (appendix, "references/skill-appendix.md"),
        ):
            fold = body.casefold()
            self.assertIn("done_without_residual", fold, name)
            self.assertIn("ended_at", fold, name)
            self.assertIn("write", fold, name)
        self.assertIn("recovery/spawn-ended-without-residual", appendix)
        source = (ROOT / "scripts" / "of" / "field.py").read_text(encoding="utf-8")
        self.assertIn("ENDED_WITHOUT_RESIDUAL", source)
        regime = (ROOT / "scripts" / "of" / "regime.py").read_text(encoding="utf-8")
        self.assertIn("class HostWriteDenial:", regime)


class SkillCursorTierRefuse(unittest.TestCase):
    """SKILL / /of teach cursor tier-only refuses; pass --model; no invented alias."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_cursor_tier_refuse(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("cursor", table)
        self.assertIn("refuses", table)
        self.assertIn("--model", table)
        self.assertIn("no alias", table)
        for body, name in (
            (core, "SKILL.md"),
            (alias, "of/SKILL.md"),
            (appendix, "references/skill-appendix.md"),
        ):
            fold = body.casefold()
            self.assertIn("cursor", fold, name)
            self.assertIn("refuses", fold, name)
            self.assertIn("--model", fold, name)
            self.assertIn("no", fold, name)
            self.assertIn("alias", fold, name)
        self.assertIn("recovery/cursor-tier-model", appendix)
        source = (ROOT / "scripts" / "of_adapters.py").read_text(encoding="utf-8")
        self.assertIn("TIER_NEED_MODEL", source)
        self.assertIn("require_named_model", source)


class SkillOperatorAction(unittest.TestCase):
    """SKILL / /of teach yolo + inherit as audited operator actions."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_alias_appendix_teach_operator_actions(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("of_trust=yolo", table)
        self.assertIn("of_spawn_env=inherit", table)
        self.assertIn("must ask", table)
        self.assertIn("operator action", table)
        self.assertIn("not silent defaults", table)
        self.assertIn("never invent", table)
        for body, name in (
            (core, "SKILL.md"),
            (alias, "of/SKILL.md"),
            (appendix, "references/skill-appendix.md"),
        ):
            fold = body.casefold()
            self.assertIn("operator action", fold, name)
            self.assertIn("of_trust=yolo", fold, name)
            self.assertIn("of_spawn_env=inherit", fold, name)
            self.assertIn("not silent", fold, name)
            self.assertIn("must ask", fold, name)
        source = (ROOT / "scripts" / "of_adapters.py").read_text(encoding="utf-8")
        self.assertIn("class OperatorAction:", source)
        self.assertIn("not silent defaults", source)


class SkillSurfaceCore(unittest.TestCase):
    """Always-loaded SKILL.md is a short core. Appendix keeps full procedure."""

    def test_core_is_under_cap_and_points_at_appendix(self) -> None:
        self.assertEqual(SkillSurface.errors(ROOT), [])
        self.assertLessEqual(
            SkillSurface.core_bytes(ROOT), SkillSurface.CORE_MAX_BYTES
        )
        self.assertLess(
            SkillSurface.core_bytes(ROOT),
            20_000,
            "core must stay a cut vs the 62477-byte 0.7.65 monolith",
        )
        core = SkillSurface.core(ROOT)
        self.assertIn("Hosts load this file only", core)
        self.assertIn(SkillSurface.APPENDIX, core)
        self.assertIn("## What to type next", core)
        alias = SkillSurface.alias(ROOT)
        self.assertIn(SkillSurface.APPENDIX, alias)

    def test_leader_surface_keeps_kernel_verbs(self) -> None:
        leader = SkillSurface.leader(ROOT)
        for needle in (
            "of resume",
            "of pack",
            "of spawn",
            "of collect",
            "of integrate",
            "of contrast",
            "of close --checklist",
            "of issue",
            "**Stay-on-the-run.**",
            "## Forbidden",
            "Do not pack a whole phase as one slice",
        ):
            self.assertIn(needle, leader, needle)

    def test_install_copies_appendix(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="of-skill-surface-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        proc = run(ROOT, "bash", str(INSTALL), "--root", str(tmp), "--generic")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        dest = tmp / ".agents" / "skills" / "orderfield"
        self.assertTrue((dest / SkillSurface.CORE).is_file())
        self.assertTrue((dest / SkillSurface.APPENDIX).is_file())
        installed = (dest / SkillSurface.CORE).read_text(encoding="utf-8")
        self.assertIn(SkillSurface.APPENDIX, installed)


if __name__ == "__main__":
    unittest.main()
