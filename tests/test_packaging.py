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
from living_map import LivingMap, SkillEfficiencyMix, SkillHarnessMix  # noqa: E402
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
    """One VERSION per real cut. Packaging-only lockstep dies. of eval --kernel."""

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

    def test_policy_docs_name_the_gate(self) -> None:
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        publish = (ROOT / "PUBLISH.md").read_text(encoding="utf-8")
        evals = (ROOT / "evals" / "README.md").read_text(encoding="utf-8")
        self.assertIn("One VERSION per real cut", contributing)
        self.assertIn("check_packaging_bump.py", contributing)
        self.assertIn("PackagingBumpDiscipline", contributing)
        self.assertIn("one VERSION per real cut", publish)
        self.assertIn("check_packaging_bump.py", publish)
        self.assertIn("PackagingBumpDiscipline", evals)
        self.assertIn("check_packaging_bump.py", evals)


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
        hero = text[:install]
        for needle in (
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
        ):
            self.assertIn(needle, hero)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        alias = (ROOT / "of" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("typical problems", skill.casefold())
        self.assertIn("typical problems", alias.casefold())
        self.assertIn("mid-flight", skill.casefold())
        self.assertIn("mid-flight", alias.casefold())


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
    """SKILL teaches timeout / idempotency / health as VERIFIED_CONTRACT."""

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
        self.assertIn("verified_contract", table)
        self.assertIn("contractsurface", table.replace(" ", "").replace("`", ""))
        alias_fold = alias.casefold()
        self.assertIn("timeout", alias_fold)
        self.assertIn("idempoten", alias_fold)
        self.assertIn("health", alias_fold)
        self.assertIn("verified_contract", alias_fold)
        appendix_fold = appendix.casefold()
        self.assertIn("timeout", appendix_fold)
        self.assertIn("idempoten", appendix_fold)
        self.assertIn("/health", appendix_fold)
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
    """Claim shipped requires contrast RESOLVED + residual empty. Mechanical."""

    @staticmethod
    def table(skill: str) -> str:
        return skill.split("## What to type next", 1)[1].split("## When to use", 1)[0]

    def test_core_and_alias_refuse_shipped_without_disk_facts(self) -> None:
        core = SkillSurface.core(ROOT)
        alias = SkillSurface.alias(ROOT)
        appendix = SkillSurface.appendix(ROOT)
        table = self.table(core).casefold()
        self.assertIn("claim shipped", table)
        self.assertIn("of contrast", table)
        self.assertIn("of close --checklist", table)
        self.assertIn("residual empty", table)
        self.assertIn("mechanical", table)
        self.assertIn("not your judgment", table)
        self.assertIn("quote-pulse", table)
        self.assertIn("Anti-done-theater", core)
        self.assertIn("mechanical", core.casefold())
        alias_fold = alias.casefold()
        self.assertIn("claim shipped", alias_fold)
        self.assertIn("of contrast", alias_fold)
        self.assertIn("of close --checklist", alias_fold)
        self.assertIn("mechanical", alias_fold)
        self.assertIn(
            "do not claim shipped unless contrast RESOLVED and residual empty",
            appendix,
        )
        self.assertIn("mechanical", appendix.casefold())
        self.assertIn("not your judgment", appendix.casefold())


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
