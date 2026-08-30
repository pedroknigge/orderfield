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

SRC="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
cleanup_src=""

have_local() {
  [[ -n "${SRC}" && -f "${SRC}/SKILL.md" && -f "${SRC}/scripts/of.py" ]]
}

if ! have_local; then
  SRC="$(mktemp -d "${TMPDIR:-/tmp}/orderfield-install.XXXXXX")"
  cleanup_src="$SRC"
  git clone --depth 1 "$REPO_URL" "$SRC" >/dev/null
fi

trap '[[ -n "$cleanup_src" ]] && rm -rf "$cleanup_src"' EXIT

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
}

remove_one() {
  local dest="$1"
  if [[ -d "$dest" ]]; then
    rm -rf "$dest"
    echo "removed $dest"
    return 0
  fi
  return 1
}

codex_pointer_block() {
  cat <<'EOF'
# orderfield skill

Install location (full skill + kernel): `~/.agents/skills/orderfield/`

Use when orchestrating agents with Haken slaving, an ORDER field, or agent waves.
Slash / invoke: `/orderfield`

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
echo "copied to $copied skill dir(s)"
echo "generic: $base/.agents/skills/$NAME"
echo "kernel: python3 $SRC/scripts/of.py status"
