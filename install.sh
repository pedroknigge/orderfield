#!/usr/bin/env bash
# Install orderfield into Agent Skills directories.
# Always lands in .agents/skills (generic). Also copies into known harnesses.
set -euo pipefail

NAME="orderfield"
REPO_URL="${ORDERFIELD_REPO:-https://github.com/pedroknigge/orderfield.git}"
# INSTALL-001: remote fetch pins this release; keep in lockstep with VERSION.
DEFAULT_VERSION="0.7.17"
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

  A checkout next to this script is installed as-is. A remote install
  fetches a tag-pinned GitHub release archive and verifies SHA-256.
  It does not clone unsigned mutable main.

  Pin / verify (remote only):
    ORDERFIELD_REF / ORDERFIELD_VERSION   release tag (default: v<VERSION>)
    ORDERFIELD_ARCHIVE / ORDERFIELD_SHA256  local archive + expected hash
    ORDERFIELD_SHA256SUMS                 local SHA256SUMS file
    ORDERFIELD_RELEASE_BASE               override release asset base URL

  Uninstall without a checkout: download+verify install.sh (see PUBLISH.md),
  then: bash install.sh --uninstall
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

if [[ -d "$base" ]]; then
  base="$(cd "$base" && pwd -P)"
elif [[ "$UNINSTALL" -eq 1 ]]; then
  echo "removed from 0 location(s)"
  exit 0
else
  mkdir -p "$base"
  base="$(cd "$base" && pwd -P)"
fi

SRC="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
cleanup_src=""

have_local() {
  [[ -n "${SRC}" && -f "${SRC}/SKILL.md" && -f "${SRC}/scripts/of.py" ]]
}

resolve_pin() {
  PINNED_VERSION="${ORDERFIELD_VERSION:-$DEFAULT_VERSION}"
  PINNED_REF="${ORDERFIELD_REF:-v${PINNED_VERSION}}"
  if [[ -n "${ORDERFIELD_REF:-}" && -z "${ORDERFIELD_VERSION:-}" ]]; then
    PINNED_VERSION="${PINNED_REF#v}"
  fi
}

mutable_ref() {
  case "$1" in
    main|master|HEAD|origin/main|origin/master|refs/heads/main|refs/heads/master)
      return 0 ;;
    *)
      return 1 ;;
  esac
}

lower_hex() {
  printf '%s' "$1" | tr 'ABCDEF' 'abcdef'
}

is_sha256() {
  local h
  h="$(lower_hex "$1")"
  [[ ${#h} -eq 64 ]] || return 1
  [[ "$h" != *[!0-9a-f]* ]] || return 1
  return 0
}

sha256_of() {
  local f="$1" out
  if command -v sha256sum >/dev/null 2>&1; then
    out="$(sha256sum "$f" | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    out="$(shasum -a 256 "$f" | awk '{print $1}')"
  elif command -v openssl >/dev/null 2>&1; then
    out="$(openssl dgst -sha256 "$f" | awk '{print $NF}')"
  elif command -v python3 >/dev/null 2>&1; then
    out="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$f")"
  else
    echo "install.sh: need sha256sum, shasum, openssl, or python3" >&2
    exit 1
  fi
  if [[ -z "$out" ]]; then
    echo "install.sh: empty SHA-256 for $f" >&2
    exit 1
  fi
  printf '%s\n' "$out"
}

fetch_url() {
  local url="$1" dest="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$dest"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$dest" "$url"
  else
    echo "install.sh: need curl or wget to fetch $url" >&2
    exit 1
  fi
}

expected_sha256_from_sums() {
  local sums="$1" name="$2"
  awk -v n="$name" '
    NF >= 2 {
      f=$NF
      sub(/^\*/, "", f)
      if (f == n) { print $1; exit }
    }
  ' "$sums"
}

github_release_base() {
  local url="${REPO_URL%.git}"
  printf '%s/releases/download/%s\n' "$url" "$PINNED_REF"
}

pinned_source_root() {
  local dest="$1" d
  if [[ -f "$dest/SKILL.md" && -f "$dest/scripts/of.py" ]]; then
    printf '%s\n' "$dest"
    return 0
  fi
  for d in "$dest"/*; do
    if [[ -d "$d" && -f "$d/SKILL.md" && -f "$d/scripts/of.py" ]]; then
      printf '%s\n' "$d"
      return 0
    fi
  done
  echo "install.sh: pinned archive is missing SKILL.md + scripts/of.py" >&2
  return 1
}

fetch_pinned_source() {
  local dest="$1" archive sums_file expected actual archive_name release_base
  resolve_pin
  if mutable_ref "$PINNED_REF"; then
    echo "install.sh: refusing unsigned mutable ref '$PINNED_REF'" >&2
    echo "install.sh: set ORDERFIELD_REF to a release tag (e.g. v${DEFAULT_VERSION})" >&2
    exit 2
  fi
  archive_name="orderfield-${PINNED_VERSION}.tar.gz"
  release_base="${ORDERFIELD_RELEASE_BASE:-$(github_release_base)}"
  archive="${dest}/.orderfield-src.tar.gz"
  if [[ -n "${ORDERFIELD_ARCHIVE:-}" ]]; then
    cp "${ORDERFIELD_ARCHIVE}" "$archive"
  else
    fetch_url "${ORDERFIELD_ARCHIVE_URL:-${release_base}/${archive_name}}" "$archive"
  fi
  if [[ -n "${ORDERFIELD_SHA256:-}" ]]; then
    expected="${ORDERFIELD_SHA256}"
  elif [[ -n "${ORDERFIELD_SHA256SUMS:-}" ]]; then
    expected="$(expected_sha256_from_sums "${ORDERFIELD_SHA256SUMS}" "$archive_name")"
  elif [[ -n "${ORDERFIELD_ARCHIVE:-}" ]]; then
    echo "install.sh: ORDERFIELD_ARCHIVE requires ORDERFIELD_SHA256 or ORDERFIELD_SHA256SUMS" >&2
    exit 1
  else
    sums_file="${dest}/.orderfield-SHA256SUMS"
    fetch_url "${ORDERFIELD_SUMS_URL:-${release_base}/SHA256SUMS}" "$sums_file"
    expected="$(expected_sha256_from_sums "$sums_file" "$archive_name")"
    rm -f "$sums_file"
  fi
  if [[ -z "$expected" ]]; then
    echo "install.sh: SHA256SUMS has no entry for ${archive_name}" >&2
    exit 1
  fi
  if ! is_sha256 "$expected"; then
    echo "install.sh: invalid SHA-256 '$expected'" >&2
    exit 1
  fi
  actual="$(sha256_of "$archive")"
  if [[ "$(lower_hex "$actual")" != "$(lower_hex "$expected")" ]]; then
    echo "install.sh: SHA-256 mismatch for ${archive_name}" >&2
    echo "install.sh: expected ${expected}" >&2
    echo "install.sh: actual   ${actual}" >&2
    exit 1
  fi
  tar -xzf "$archive" -C "$dest"
  rm -f "$archive"
}

# Uninstall only deletes dests; no fetch required.
if [[ "$UNINSTALL" -eq 0 ]] && ! have_local; then
  SRC="$(mktemp -d "${TMPDIR:-/tmp}/orderfield-install.XXXXXX")"
  cleanup_src="$SRC"
  fetch_pinned_source "$SRC"
  SRC="$(pinned_source_root "$SRC")"
fi

# A literal `./install.sh --project` installs below its own checkout. Copy from
# an external snapshot so the destination cannot recurse into the source while
# it is being populated. The snapshot also drops leftovers from older local
# project installs.
if [[ "$UNINSTALL" -eq 0 && -z "$cleanup_src" ]]; then
  case "$base/" in
    "$SRC/"*)
      staged_src="$(mktemp -d "${TMPDIR:-/tmp}/orderfield-install.XXXXXX")"
      cleanup_src="$staged_src"
      if command -v rsync >/dev/null 2>&1; then
        rsync -a \
          --exclude .git \
          --exclude .orderfield \
          --exclude .agents \
          --exclude .claude \
          --exclude .codex \
          --exclude .cursor \
          --exclude .opencode \
          --exclude .grok \
          --exclude .gemini \
          --exclude .local \
          --exclude '__pycache__' \
          "$SRC/" "$staged_src/"
      else
        cp -R "$SRC"/. "$staged_src/"
        rm -rf \
          "$staged_src/.git" \
          "$staged_src/.orderfield" \
          "$staged_src/.agents" \
          "$staged_src/.claude" \
          "$staged_src/.codex" \
          "$staged_src/.cursor" \
          "$staged_src/.opencode" \
          "$staged_src/.grok" \
          "$staged_src/.gemini" \
          "$staged_src/.local"
        find "$staged_src" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
      fi
      SRC="$staged_src"
      ;;
  esac
fi

trap '[[ -n "$cleanup_src" ]] && rm -rf "$cleanup_src"' EXIT

alias_skill_md() {
  # Keep classic installs identical to the repository-owned npx alias surface.
  cat "$SRC/of/SKILL.md"
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

Use when explicitly invoked, when `.orderfield/ORDER.json` exists, or for a
genuinely multi-slice / multi-writer wave. A harness name alone or one ordinary
subagent is not a trigger.
Slash / invoke: `/orderfield` (alias: `/of`)

Unknown harnesses: `of spawn --adapter generic` (or `OF_AGENT='your-cli …'`).
If the skill folder is missing: `npx skills add pedroknigge/orderfield -g -y --full-depth -s '*'`
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

# Iterate dests in this shell so copied/removed persist. Command
# substitution into a here-doc, not process substitution.
install_agy_dests() {
  local dest parent agy_bin=0
  if [[ "$MODE" == "global" ]] && command -v agy >/dev/null 2>&1; then
    agy_bin=1
  fi
  while IFS= read -r dest; do
    [[ -n "$dest" ]] || continue
    parent="$(dirname "$(dirname "$dest")")"
    if [[ "$agy_bin" -eq 1 || -d "$parent" ]]; then
      copy_one "$dest"
      copied=$((copied + 1))
    fi
  done <<EOF
$(agy_dests)
EOF
}

uninstall_agy_dests() {
  local dest
  while IFS= read -r dest; do
    [[ -n "$dest" ]] || continue
    if remove_one "$dest"; then
      removed=$((removed + 1))
    fi
  done <<EOF
$(agy_dests)
EOF
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
