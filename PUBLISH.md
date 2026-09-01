# Publish notes

**STAR**

- **Situation:** A tagged GitHub release must match VERSION, both skill entry points, and the installed kernel.
- **Task:** Gate publish: tests, `validate-skill.sh`, package discovery of `orderfield` and `of`, then tag.
- **Action:** Land through protected `main`, annotated tag, `gh release create --verify-tag`, then mortal install.
- **Result:** Remote install reports the same version as `VERSION` and both skill names resolve.

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

Verify the remote tag target and published release before calling the release complete:

```bash
git fetch origin main --tags
test "$(git rev-list -n 1 "$release_tag")" = "$(git rev-parse origin/main)"
test "$(gh release view "$release_tag" --json tagName --jq .tagName)" = "$release_tag"
test -n "$(gh release view "$release_tag" --json publishedAt --jq .publishedAt)"
gh release view "$release_tag" --json url,tagName,isDraft,isPrerelease,publishedAt
```

## Mortal install (after push)

```bash
npx skills add pedroknigge/orderfield -g -y --full-depth -s '*' -a '*'
# or
curl -fsSL https://raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh | bash
```

Confirm the published source still exposes both skill names and that the remote classic installer reports the release version:

```bash
npx --yes skills add pedroknigge/orderfield --list --full-depth
remote_root="$(mktemp -d)"
curl -fsSL https://raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh | bash -s -- --root "$remote_root"
grep -q "version: \"$release_version\"" "$remote_root/.agents/skills/orderfield/SKILL.md"
grep -q "version: \"$release_version\"" "$remote_root/.agents/skills/of/SKILL.md"
"$remote_root/.local/bin/of" --help
```
