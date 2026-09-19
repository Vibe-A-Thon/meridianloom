#!/usr/bin/env sh
# Meridian Loom installer for macOS and Linux.
#
# Installs: a PRIVATE Python runtime for Meridian's own dependencies, the VS Code
# extension, an optional Premium licence, and a `meridian` command.
#
#   sh install.sh                                   # typical
#   sh install.sh --licence ~/acme.mlic             # with a Premium licence
#   sh install.sh --no-extension --wheelhouse /wheels --licence acme.mlic --machine-wide
#   sh install.sh --dry-run                         # show what would happen
#
# It never installs into your system Python or a project environment, and it
# sends nothing anywhere. The only network use is pip downloading the pinned
# dependencies (none with --wheelhouse). Re-running is safe: an up-to-date
# runtime is kept, a changed one is rebuilt.
#
# POSIX sh only: no bashisms, so it runs under macOS's bash 3.2, dash and ash.

set -eu

MIN_MAJOR=3
MIN_MINOR=11

VSIX=""
LICENCE=""
MACHINE_WIDE=0
PYTHON=""
CODE=""
NO_EXTENSION=0
WHEELHOUSE=""
INDEX_URL=""
PREFIX=""
FORCE=0
DRY_RUN=0
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

usage() {
    cat <<'EOF'
Usage: sh install.sh [options]

  --vsix FILE        meridian-loom-*.vsix (default: newest next to this script or in ../dist)
  --licence FILE     install a Premium licence (.mlic)
  --machine-wide     install the licence for every account on this machine (uses sudo)
  --python PATH      Python 3.11+ to build the runtime from
  --code CMD         VS Code command-line tool (code, code-insiders, codium)
  --no-extension     runtime and CLI only; do not touch VS Code (servers, CI)
  --wheelhouse DIR   folder of pre-downloaded wheels: install fully offline
  --index-url URL    alternative package index (internal mirror)
  --prefix DIR       install the runtime here instead of the default location
  --force            rebuild the runtime even if it looks current
  --dry-run          show what would happen; change nothing
  -h, --help         this text
EOF
}

say()  { printf '==> %s\n' "$*"; }
ok()   { printf '    ok: %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --vsix)         [ $# -ge 2 ] || die "--vsix needs a value"; VSIX=$2; shift 2 ;;
        --licence|--license) [ $# -ge 2 ] || die "$1 needs a value"; LICENCE=$2; shift 2 ;;
        --machine-wide) MACHINE_WIDE=1; shift ;;
        --python)       [ $# -ge 2 ] || die "--python needs a value"; PYTHON=$2; shift 2 ;;
        --code)         [ $# -ge 2 ] || die "--code needs a value"; CODE=$2; shift 2 ;;
        --no-extension) NO_EXTENSION=1; shift ;;
        --wheelhouse)   [ $# -ge 2 ] || die "--wheelhouse needs a value"; WHEELHOUSE=$2; shift 2 ;;
        --index-url)    [ $# -ge 2 ] || die "--index-url needs a value"; INDEX_URL=$2; shift 2 ;;
        --prefix)       [ $# -ge 2 ] || die "--prefix needs a value"; PREFIX=$2; shift 2 ;;
        --force)        FORCE=1; shift ;;
        --dry-run)      DRY_RUN=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              usage >&2; die "unknown option: $1" ;;
    esac
done

# run CMD...: execute, or just print under --dry-run.
run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '    [dry-run] would run: %s\n' "$*"
    else
        "$@"
    fi
}

# -- locations -----------------------------------------------------------------
OS=$(uname -s)
case "$OS" in
    Linux)  DEFAULT_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/meridian-loom" ;;
    Darwin) DEFAULT_ROOT="$HOME/Library/Application Support/MeridianLoom" ;;
    MINGW*|MSYS*|CYGWIN*) die "this is a Windows shell; use install.ps1 (PowerShell) instead" ;;
    *)      die "unsupported operating system: $OS (supported: Linux, macOS; Windows uses install.ps1)" ;;
esac
ROOT=${PREFIX:-$DEFAULT_ROOT}
RUNTIME_DIR="$ROOT/runtime"
VENV_DIR="$RUNTIME_DIR/venv"
VENV_PY="$VENV_DIR/bin/python"
SIDECAR_DIR="$ROOT/sidecar"
BIN_DIR="$ROOT/bin"
STAMP="$RUNTIME_DIR/STAMP"

# -- 1. Python ------------------------------------------------------------------
python_ok() {
    # Prints "MAJOR.MINOR" and returns 0 when $1 is a usable Python >= 3.11.
    ver=$("$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || return 1
    major=${ver%%.*}
    minor=${ver#*.}
    case "$major$minor" in *[!0-9]*|"") return 1 ;; esac
    if [ "$major" -gt "$MIN_MAJOR" ] || { [ "$major" -eq "$MIN_MAJOR" ] && [ "$minor" -ge "$MIN_MINOR" ]; }; then
        printf '%s' "$ver"
        return 0
    fi
    return 1
}

say "Looking for Python"
PY=""
PYVER=""
if [ -n "$PYTHON" ]; then
    PYVER=$(python_ok "$PYTHON") || die "$PYTHON is not Python $MIN_MAJOR.$MIN_MINOR or newer"
    PY=$PYTHON
else
    for candidate in python3.13 python3.12 python3.11 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if PYVER=$(python_ok "$candidate"); then PY=$(command -v "$candidate"); break; fi
        fi
    done
fi
if [ -z "$PY" ]; then
    case "$OS" in
        Darwin) hint="brew install python@3.12" ;;
        *)      hint="sudo apt install python3 python3-venv   (Debian/Ubuntu)  |  sudo dnf install python3   (Fedora/RHEL)" ;;
    esac
    die "Python $MIN_MAJOR.$MIN_MINOR or newer was not found. Install it ($hint), then re-run, or pass --python PATH."
fi
ok "Python $PYVER at $PY"

# -- 2. VS Code + package -------------------------------------------------------
find_vsix() {
    for dir in "$HERE" "$HERE/../dist"; do
        [ -d "$dir" ] || continue
        # newest by modification time
        latest=$(ls -t "$dir"/meridian-loom-*.vsix 2>/dev/null | head -n 1 || true)
        if [ -n "$latest" ]; then printf '%s' "$latest"; return 0; fi
    done
    return 1
}

CODE_CMD=""
if [ "$NO_EXTENSION" -eq 0 ]; then
    say "Looking for VS Code"
    if [ -n "$CODE" ]; then
        command -v "$CODE" >/dev/null 2>&1 || [ -x "$CODE" ] || die "VS Code CLI not found: $CODE"
        CODE_CMD=$CODE
    else
        for candidate in code code-insiders codium; do
            if command -v "$candidate" >/dev/null 2>&1; then CODE_CMD=$candidate; break; fi
        done
        if [ -z "$CODE_CMD" ] && [ "$OS" = "Darwin" ]; then
            mac="/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
            [ -x "$mac" ] && CODE_CMD=$mac
        fi
    fi
    [ -n "$CODE_CMD" ] || die "VS Code's command-line tool was not found. Install VS Code (macOS: run 'Shell Command: Install code command in PATH' from its palette), pass --code PATH, or use --no-extension."
    ok "VS Code CLI: $CODE_CMD"
fi

if [ -z "$VSIX" ]; then VSIX=$(find_vsix) || die "No meridian-loom-*.vsix found. Pass --vsix FILE."; fi
[ -f "$VSIX" ] || die "package not found: $VSIX"
ok "package: $VSIX"

# -- 3. integrity ---------------------------------------------------------------
SUMS="$(dirname -- "$VSIX")/SHA256SUMS"
if [ -f "$SUMS" ]; then
    say "Verifying the package checksum"
    name=$(basename -- "$VSIX")
    expected=$(grep -F "$name" "$SUMS" | head -n 1 | awk '{print tolower($1)}' || true)
    if [ -z "$expected" ]; then
        note "SHA256SUMS does not list $name; skipping."
    else
        if command -v sha256sum >/dev/null 2>&1; then actual=$(sha256sum "$VSIX" | awk '{print $1}')
        elif command -v shasum >/dev/null 2>&1; then actual=$(shasum -a 256 "$VSIX" | awk '{print $1}')
        else die "need sha256sum or shasum to verify the package (or remove $SUMS)"; fi
        [ "$expected" = "$actual" ] || die "Checksum mismatch for $name. Expected $expected, got $actual. Do not install this file."
        ok "SHA-256 matches"
    fi
else
    note "No SHA256SUMS next to the package; integrity not checked (see docs/DEPLOYMENT.md)."
fi

# -- 4. runtime -----------------------------------------------------------------
say "Preparing the private Python runtime"
REQ="$HERE/requirements.txt"
USE_LOCK=0
if [ -f "$HERE/requirements.lock" ]; then REQ="$HERE/requirements.lock"; USE_LOCK=1; fi
[ -f "$REQ" ] || die "missing $REQ"
if command -v sha256sum >/dev/null 2>&1; then REQ_HASH=$(sha256sum "$REQ" | awk '{print $1}')
elif command -v shasum >/dev/null 2>&1; then REQ_HASH=$(shasum -a 256 "$REQ" | awk '{print $1}')
else REQ_HASH=$(cksum "$REQ" | awk '{print $1}'); fi
WANTED="$REQ_HASH|$PYVER"

CURRENT=0
if [ "$FORCE" -eq 0 ] && [ -f "$STAMP" ] && [ -x "$VENV_PY" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$WANTED" ]; then
    CURRENT=1
fi

if [ "$CURRENT" -eq 1 ]; then
    ok "runtime is up to date ($VENV_DIR)"
else
    if [ "$DRY_RUN" -eq 1 ]; then
        note "[dry-run] would create $VENV_DIR and install $(basename -- "$REQ")"
    else
        rm -rf "$VENV_DIR"
        mkdir -p "$RUNTIME_DIR"
        "$PY" -m venv "$VENV_DIR" || die "Could not create the virtual environment. On Debian/Ubuntu install the venv module: sudo apt install python3-venv"
        note "installing dependencies (this can take a few minutes)..."
        set -- -m pip install --disable-pip-version-check --no-input -r "$REQ"
        [ "$USE_LOCK" -eq 1 ] && set -- "$@" --require-hashes
        if [ -n "$WHEELHOUSE" ]; then set -- "$@" --no-index --find-links "$WHEELHOUSE"
        elif [ -n "$INDEX_URL" ]; then set -- "$@" --index-url "$INDEX_URL"; fi
        "$VENV_PY" "$@" || die "pip could not install the dependencies. Behind a proxy set HTTPS_PROXY; offline: --wheelhouse DIR; internal mirror: --index-url URL."
        printf '%s' "$WANTED" > "$STAMP"
    fi
    ok "runtime ready ($VENV_DIR)"
fi

# -- 5. sidecar sources + launcher ---------------------------------------------
say "Unpacking the sidecar and writing the meridian command"
MERIDIAN="$BIN_DIR/meridian"
if [ "$DRY_RUN" -eq 1 ]; then
    note "[dry-run] would unpack $VSIX, copy extension/sidecar to $SIDECAR_DIR/<version>, write $MERIDIAN"
else
    TMP=$(mktemp -d 2>/dev/null || mktemp -d -t meridian-install)
    trap 'rm -rf "$TMP"' EXIT INT TERM
    "$PY" -m zipfile -e "$VSIX" "$TMP" || die "could not unpack $VSIX (is it a valid .vsix?)"
    [ -d "$TMP/extension/sidecar" ] || die "the package has no extension/sidecar folder"
    VERSION=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$TMP/extension/package.json")
    TARGET="$SIDECAR_DIR/$VERSION"
    rm -rf "$TARGET"
    mkdir -p "$TARGET" "$BIN_DIR"
    cp -R "$TMP/extension/sidecar/." "$TARGET/"
    {
        printf '#!/bin/sh\n'
        printf '# Meridian Loom command line (generated by install.sh)\n'
        printf "PYTHONPATH='%s' exec '%s' -m meridian_core.cli \"\$@\"\n" "$TARGET" "$VENV_PY"
    } > "$MERIDIAN"
    chmod 755 "$MERIDIAN"
    ok "sidecar $VERSION at $TARGET"
fi

# -- 6. extension ---------------------------------------------------------------
if [ "$NO_EXTENSION" -eq 0 ]; then
    say "Installing the VS Code extension"
    run "$CODE_CMD" --install-extension "$VSIX" --force
    [ "$DRY_RUN" -eq 1 ] || ok "extension installed"
fi

# -- 7. licence -----------------------------------------------------------------
if [ -n "$LICENCE" ]; then
    say "Installing the Premium licence"
    [ -f "$LICENCE" ] || die "Licence file not found: $LICENCE"
    LICENCE_ABS=$(CDPATH= cd -- "$(dirname -- "$LICENCE")" && pwd)/$(basename -- "$LICENCE")
    if [ "$MACHINE_WIDE" -eq 1 ]; then
        if [ "$(id -u)" -eq 0 ]; then
            run "$MERIDIAN" licence install "$LICENCE_ABS" --scope machine
        elif command -v sudo >/dev/null 2>&1; then
            note "a machine-wide licence is written under /etc or /Library, which needs administrator rights (sudo)."
            run sudo "$MERIDIAN" licence install "$LICENCE_ABS" --scope machine
        else
            die "--machine-wide needs root and sudo is not available; re-run as root."
        fi
    else
        run "$MERIDIAN" licence install "$LICENCE_ABS" --scope user \
            || die "The licence was not installed (see the reason above). Community features are unaffected."
    fi
else
    note "No licence supplied: the free Community edition is active. Add one any time:"
    note "  meridian licence install <file.mlic>     (or 'Meridian Loom: Licence' in VS Code)"
fi

# -- 8. verify -------------------------------------------------------------------
say "Checking the installation"
if [ "$DRY_RUN" -eq 1 ]; then
    note "[dry-run] no changes were made."
else
    "$MERIDIAN" licence status
    probe=$("$VENV_PY" -c 'import cryptography, yaml, jsonschema, langgraph, tree_sitter; print("runtime imports ok")' 2>&1) \
        || die "The runtime cannot import its dependencies: $probe"
    ok "$probe"
    printf '\nMeridian Loom is installed.\n'
    [ "$NO_EXTENSION" -eq 0 ] && printf '  Reload VS Code, then open the Meridian Loom view (or run "Meridian Loom: Doctor").\n'
    printf '  Command line: %s   (add %s to PATH to type just: meridian)\n' "$MERIDIAN" "$BIN_DIR"
    [ -n "$PREFIX" ] && printf '  Custom location: set the VS Code setting meridian.python.interpreterPath to %s\n' "$VENV_PY"
fi
exit 0
