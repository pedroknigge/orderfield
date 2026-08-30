#!/usr/bin/env bash
# Install orderfield into Agent Skills directories.
# Always lands in .agents/skills (generic). Also copies into known harnesses.
set -euo pipefail

NAME="orderfield"
REPO_URL="${ORDERFIELD_REPO:-https://github.com/pedroknigge/orderfield.git}"
KNOWN_HARNESSES=(claude codex cursor opencode grok)
# agy is not a KNOWN_HARNESSES entry; dests are under .gemini/ (see agy_dests).
BEGIN_MARKER="<!-- BEGIN orderfield skill -->"
END_MARKER="<!-- END orderfield skill -->"

MODE="auto"
UNINSTALL=0
GENERIC_ONLY=0
base=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global) MODE="global"; shift ;;
    --project) MODE="project"; shift ;;
    --generic) GENERIC_ONLY=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --root)
      MODE="project"
      base="${2:?--root needs a path}"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: install.sh [--global|--project|--generic] [--uninstall] [--root PATH]

  --global     install under $HOME (default when no path is given)
  --project    install under the current directory
  --generic    only the portable path: .agents/skills/orderfield
  --root PATH  project-style install under PATH
  --uninstall  remove copies this script manages

  After install, creates an `of` symlink to the installed skill copy of
  scripts/of.py (not the checkout used as the install source):
    global  → ~/.local/bin/of
    --root / project → <base>/.local/bin/of (hermetic; does not touch $HOME)
  Uninstall removes that symlink when it is a symlink.

  One-liner uninstall (no local checkout needed):
    curl -fsSL https://raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh | bash -s -- --uninstall
EOF
      exit 0
      ;;
    *)
      if [[ "$1" == -* ]]; then
        echo "unknown flag: $1" >&2
        exit 2
      fi
      MODE="project"
      base="$1"
      shift
      ;;
  esac
done

if [[ -z "$base" ]]; then
  if [[ "$MODE" == "project" ]]; then
    base="."
  else
    base="$HOME"
    MODE="global"
  fi
fi

SRC="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
cleanup_src=""

have_local() {
  [[ -n "${SRC}" && -f "${SRC}/SKILL.md" && -f "${SRC}/scripts/of.py" ]]
}

# Uninstall only deletes dests; no clone required (curl | bash -s -- --uninstall).
if [[ "$UNINSTALL" -eq 0 ]] && ! have_local; then
  SRC="$(mktemp -d "${TMPDIR:-/tmp}/orderfield-install.XXXXXX")"
  cleanup_src="$SRC"
  git clone --depth 1 "$REPO_URL" "$SRC" >/dev/null
fi

trap '[[ -n "$cleanup_src" ]] && rm -rf "$cleanup_src"' EXIT

alias_skill_md() {
  # /of is a first-class alias skill: same triggers, points at the sibling dir.
  local ver
  ver="$(cat "$SRC/VERSION" 2>/dev/null | tr -d '[:space:]')"
  ver="${ver:-unknown}"
  cat <<EOF
---
name: of
description: v${ver} — Alias for orderfield. Use when the user says /of, of, orderfield, order field, Haken slaving, threshold delegation, or agent waves. Load before spawning subagents under a shared ORDER.
license: MIT
metadata:
  version: "${ver}"
  alias-of: orderfield
---

# /of — alias for orderfield

This skill is an alias. The full skill — doctrine, kernel (\`scripts/of.py\`),
SLAVE contract, schemas — lives in the sibling skill directory
\`orderfield/\` in this same skills root.

Read \`../orderfield/SKILL.md\` (relative to this file) and follow it exactly
as if it had been invoked directly.
EOF
}

write_alias_for() {
  local skill_dest="$1" alias_dest
  alias_dest="$(dirname "$skill_dest")/of"
  rm -rf "$alias_dest"
  mkdir -p "$alias_dest"
  alias_skill_md > "$alias_dest/SKILL.md"
  echo "installed $alias_dest (alias /of)"
}

copy_one() {
  local dest="$1"
  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  mkdir -p "$dest"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude .git \
      --exclude .orderfield \
      --exclude '__pycache__' \
      "$SRC/" "$dest/"
  else
    cp -R "$SRC"/. "$dest/"
    rm -rf "$dest/.git" "$dest/.orderfield"
    find "$dest" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
  fi
  echo "installed $dest"
  if [[ "$(basename "$dest")" == "$NAME" ]]; then
    write_alias_for "$dest"
  fi
}

remove_one() {
  local dest="$1" alias_dest hit=1
  if [[ -d "$dest" ]]; then
    rm -rf "$dest"
    echo "removed $dest"
    hit=0
  fi
  if [[ "$(basename "$dest")" == "$NAME" ]]; then
    alias_dest="$(dirname "$dest")/of"
    if [[ -d "$alias_dest" ]]; then
      rm -rf "$alias_dest"
      echo "removed $alias_dest"
    fi
  fi
  return $hit
}

# PATH symlink for `of`: always targets the installed skill copy (generic dest),
# never ephemeral $SRC. Global → ~/.local/bin/of; project/--root → $base/.local/bin/of
# so hermetic --root tests do not touch the real HOME.
of_bin_dir() {
  if [[ "$MODE" == "global" ]]; then
    printf '%s\n' "$HOME/.local/bin"
  else
    printf '%s\n' "$base/.local/bin"
  fi
}

of_installed_kernel() {
  printf '%s\n' "$base/.agents/skills/$NAME/scripts/of.py"
}

install_of_path() {
  local bindir link target
  target="$(of_installed_kernel)"
  if [[ ! -f "$target" ]]; then
    echo "warn: missing installed kernel at $target; skip of PATH symlink" >&2
    return 0
  fi
  chmod +x "$target" || true
  bindir="$(of_bin_dir)"
  link="$bindir/of"
  mkdir -p "$bindir"
  ln -sf "$target" "$link"
  echo "of: $link -> $target"
  if [[ "$MODE" == "global" ]]; then
    echo "Ensure ~/.local/bin is on your PATH"
  else
    echo "project of symlink at $link (use --global for ~/.local/bin/of)"
  fi
}

uninstall_of_path() {
  local bindir link
  bindir="$(of_bin_dir)"
  link="$bindir/of"
  if [[ -L "$link" ]]; then
    rm -f "$link"
    echo "removed $link"
  fi
}

codex_pointer_block() {
  cat <<'EOF'
# orderfield skill

Install location (full skill + kernel): `~/.agents/skills/orderfield/`

Use when orchestrating agents with Haken slaving, an ORDER field, or agent waves.
Slash / invoke: `/orderfield` (alias: `/of`)

Unknown harnesses: `of spawn --adapter generic` (or `OF_AGENT='your-cli …'`).
If the skill folder is missing: `npx skills add pedroknigge/orderfield -g -y`
EOF
}

strip_block() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  local tmp
  tmp="$(mktemp)"
  awk -v b="$BEGIN_MARKER" -v e="$END_MARKER" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    !skip   { print }
  ' "$file" > "$tmp"
  cat "$tmp" > "$file"
  rm -f "$tmp"
}

write_codex_pointer() {
  local agents_md="$1"
  mkdir -p "$(dirname "$agents_md")"
  touch "$agents_md"
  strip_block "$agents_md"
  {
    echo ""
    echo "$BEGIN_MARKER"
    codex_pointer_block
    echo "$END_MARKER"
    echo ""
  } >> "$agents_md"
  echo "pointer $agents_md"
}

copied=0
removed=0

install_generic() {
  copy_one "$base/.agents/skills/$NAME"
  copied=$((copied + 1))
}

uninstall_generic() {
  if remove_one "$base/.agents/skills/$NAME"; then
    removed=$((removed + 1))
  fi
}

harness_present() {
  local h="$1"
  [[ -d "$base/.$h" ]] && return 0
  case "$h" in
    claude) command -v claude >/dev/null 2>&1 ;;
    codex) command -v codex >/dev/null 2>&1 ;;
    cursor) command -v cursor >/dev/null 2>&1 || command -v agent >/dev/null 2>&1 || command -v cursor-agent >/dev/null 2>&1 ;;
    opencode) command -v opencode >/dev/null 2>&1 ;;
    grok) command -v grok >/dev/null 2>&1 || command -v grok-cli >/dev/null 2>&1 ;;
    *) return 1 ;;
  esac
}

agy_dests() {
  printf '%s\n' \
    "$base/.gemini/config/skills/$NAME" \
    "$base/.gemini/antigravity-cli/skills/$NAME"
}

install_agy_dests() {
  local dest parent agy_bin=0
  if [[ "$MODE" == "global" ]] && command -v agy >/dev/null 2>&1; then
    agy_bin=1
  fi
  while IFS= read -r dest; do
    parent="$(dirname "$(dirname "$dest")")"
    if [[ "$agy_bin" -eq 1 || -d "$parent" ]]; then
      copy_one "$dest"
      copied=$((copied + 1))
    fi
  done < <(agy_dests)
}

uninstall_agy_dests() {
  local dest
  while IFS= read -r dest; do
    if remove_one "$dest"; then
      removed=$((removed + 1))
    fi
  done < <(agy_dests)
}

if [[ "$UNINSTALL" -eq 1 ]]; then
  uninstall_generic
  for h in "${KNOWN_HARNESSES[@]}"; do
    if remove_one "$base/.$h/skills/$NAME"; then
      removed=$((removed + 1))
    fi
  done
  uninstall_agy_dests
  uninstall_of_path
  if [[ -f "$base/.codex/AGENTS.md" ]]; then
    strip_block "$base/.codex/AGENTS.md"
    echo "stripped Codex pointer"
  fi
  echo "removed from $removed location(s)"
  exit 0
fi

# Generic first: unknown agents and Codex both read ~/.agents/skills.
install_generic

if [[ "$GENERIC_ONLY" -eq 0 ]]; then
  for h in "${KNOWN_HARNESSES[@]}"; do
    if [[ "$MODE" == "project" ]]; then
      if [[ -d "$base/.$h" ]]; then
        copy_one "$base/.$h/skills/$NAME"
        copied=$((copied + 1))
      fi
    else
      if harness_present "$h"; then
        copy_one "$base/.$h/skills/$NAME"
        copied=$((copied + 1))
      fi
    fi
  done
  install_agy_dests
fi

if [[ "$MODE" == "global" && -d "$base/.codex" ]]; then
  write_codex_pointer "$base/.codex/AGENTS.md"
fi

chmod +x "$SRC/scripts/of.py" || true
install_of_path
echo "copied to $copied skill dir(s)"
echo "generic: $base/.agents/skills/$NAME"
echo "kernel: of status  # or: python3 $(of_installed_kernel) status"
