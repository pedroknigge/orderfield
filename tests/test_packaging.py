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


if __name__ == "__main__":
    unittest.main()
