# Publish notes

A release that lies about VERSION is a mood, not a ship.

The gate is tests, `validate-skill.sh`, and package discovery of both `orderfield` and `of`. Then the tag.

Land through protected `main`. Annotated tag. `gh release create --verify-tag`. Mortal install from the remote.

A cut, a resume, a different host — the published kernel is the same. The results do not have to change.

Public repo: https://github.com/pedroknigge/orderfield

## Pre-publish gate

Review the worktree before release. Unrelated user files may exist, but every tracked release change must be intentional and `git diff --check` must pass.

```bash
git status --short
git diff --check
python3 -m unittest discover -s tests -v
./scripts/validate-skill.sh
npx --yes skills add . --list --full-depth
```

All commands must exit 0. Package discovery must list both `orderfield` and `of`. `validate-skill.sh` checks VERSION, both skill entry points, README, the current architecture/audit docs, and the latest CHANGELOG heading. Preserve unrelated files rather than cleaning them away.

Run the classic installer and CLI from an isolated root:

```bash
install_root="$(mktemp -d)"
bash install.sh --root "$install_root"
test -f "$install_root/.agents/skills/orderfield/SKILL.md"
test -f "$install_root/.agents/skills/of/SKILL.md"
"$install_root/.local/bin/of" --help
```

## Tag and GitHub release

Land the release commit through protected `main`, then tag that exact commit. Do not tag a dirty or local-only tree.

```bash
release_version="$(tr -d '[:space:]' < VERSION)"
release_tag="v${release_version}"
git fetch origin main --tags
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
git tag -a "$release_tag" -m "Orderfield $release_version"
git push origin "$release_tag"
gh release create "$release_tag" --verify-tag --title "Orderfield $release_version" --notes-from-tag
```

Publish the tag-pinned installer asset and SHA-256 checksums. Do not leave curl-pipe of unsigned `main` as the only install path.

```bash
asset_dir="$(mktemp -d)"
git archive --format=tar --prefix="orderfield-${release_version}/" "$release_tag" \
  | gzip -n > "${asset_dir}/orderfield-${release_version}.tar.gz"
cp install.sh "${asset_dir}/install.sh"
(
  cd "$asset_dir"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum install.sh "orderfield-${release_version}.tar.gz" > SHA256SUMS
  else
    shasum -a 256 install.sh "orderfield-${release_version}.tar.gz" > SHA256SUMS
  fi
)
gh release upload "$release_tag" \
  "${asset_dir}/install.sh" \
  "${asset_dir}/orderfield-${release_version}.tar.gz" \
  "${asset_dir}/SHA256SUMS"
```

Verify the remote tag target, published release, and checksum assets before calling the release complete:

```bash
git fetch origin main --tags
test "$(git rev-list -n 1 "$release_tag")" = "$(git rev-parse origin/main)"
test "$(gh release view "$release_tag" --json tagName --jq .tagName)" = "$release_tag"
test -n "$(gh release view "$release_tag" --json publishedAt --jq .publishedAt)"
gh release view "$release_tag" --json url,tagName,isDraft,isPrerelease,publishedAt
test "$(gh release view "$release_tag" --json assets --jq '[.assets[].name] | sort | join(" ")')" = "SHA256SUMS install.sh orderfield-${release_version}.tar.gz"
```

## Mortal install (after push)

```bash
npx skills add pedroknigge/orderfield -g -y --full-depth -s '*' -a '*'
```

Classic install is tag-pinned and SHA-256 verified. Do not pipe unsigned `main`.

```bash
release_version="$(tr -d '[:space:]' < VERSION)"
release_tag="v${release_version}"
asset_base="https://github.com/pedroknigge/orderfield/releases/download/${release_tag}"
verify_root="$(mktemp -d)"
curl -fsSL "$asset_base/SHA256SUMS" -o "$verify_root/SHA256SUMS"
curl -fsSL "$asset_base/install.sh" -o "$verify_root/install.sh"
curl -fsSL "$asset_base/orderfield-${release_version}.tar.gz" \
  -o "$verify_root/orderfield-${release_version}.tar.gz"
python3 - "$verify_root" <<'PY'
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
wanted = {}
for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    digest, name = line.split(None, 1)
    wanted[name.lstrip("*")] = digest.lower()
for path in root.iterdir():
    if path.name == "SHA256SUMS":
        continue
    expected = wanted.get(path.name)
    if expected is None:
        raise SystemExit(f"SHA256SUMS missing {path.name}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"SHA-256 mismatch: {path.name}")
if "install.sh" not in wanted:
    raise SystemExit("SHA256SUMS missing install.sh")
print("SHA-256 ok")
PY
```

Confirm the published source still exposes both skill names and that the verified classic installer reports the release version:

```bash
npx --yes skills add pedroknigge/orderfield --list --full-depth
remote_root="$(mktemp -d)"
ORDERFIELD_REF="$release_tag" \
ORDERFIELD_VERSION="$release_version" \
ORDERFIELD_ARCHIVE="$verify_root/orderfield-${release_version}.tar.gz" \
ORDERFIELD_SHA256SUMS="$verify_root/SHA256SUMS" \
bash "$verify_root/install.sh" --root "$remote_root"
grep -q "version: \"$release_version\"" "$remote_root/.agents/skills/orderfield/SKILL.md"
grep -q "version: \"$release_version\"" "$remote_root/.agents/skills/of/SKILL.md"
"$remote_root/.local/bin/of" --help
```

## Residuals (not kernel)

These are publish/ecosystem limits. They are not Orderfield defects. Do not invent kernel code to close them. Durable auditor note: [docs/audit/out-of-scope.md](docs/audit/out-of-scope.md).

**npx pin (SCOPE-NPX).** `npx skills add pedroknigge/orderfield` follows whatever the skills CLI resolves from the GitHub repo. There is no versioned source argument until that ecosystem supports one. Do not fake a pin in this tree. The pin path is the classic installer: tag-pinned archive + SHA-256 (`ORDERFIELD_REF` / `ORDERFIELD_ARCHIVE` / `ORDERFIELD_SHA256SUMS` above).

**Signing / immutable releases (SCOPE-SIGN).** Tag signing, attestation, and GitHub `immutable=true` releases are publish-process, not kernel. Classic install is already tag-pinned and SHA-256 verified (`install.sh`, `orderfield-<ver>.tar.gz`, `SHA256SUMS` on the GitHub release). Do not add cosign/sigstore/signing code to the stdlib CLI. Residual stays here until a human publish process adds those artifacts.
