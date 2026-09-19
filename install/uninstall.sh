#!/usr/bin/env sh
# Removes what install.sh installed. Lists by default; --yes actually removes.
#
# Removes the VS Code extension, the private Python runtime, the unpacked sidecar
# and the `meridian` launcher. It does NOT touch:
#   * your recorded evidence (each workspace's .meridian folder) - that is yours.
#     To remove it: `meridian uninstall --workspace DIR --yes`, BEFORE running
#     this script (it needs the launcher this script deletes);
#   * your Premium licence, unless --purge-licence is given.
#
#   sh uninstall.sh            # list what would be removed
#   sh uninstall.sh --yes      # remove it

set -eu

YES=0
CODE=""
NO_EXTENSION=0
PREFIX=""
PURGE_LICENCE=0
EXTENSION_ID="meridianloom.meridian-loom"

while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y)         YES=1; shift ;;
        --code)           [ $# -ge 2 ] || { echo "--code needs a value" >&2; exit 1; }; CODE=$2; shift 2 ;;
        --no-extension)   NO_EXTENSION=1; shift ;;
        --prefix)         [ $# -ge 2 ] || { echo "--prefix needs a value" >&2; exit 1; }; PREFIX=$2; shift 2 ;;
        --purge-licence|--purge-license) PURGE_LICENCE=1; shift ;;
        -h|--help)
            sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 1 ;;
    esac
done

case "$(uname -s)" in
    Linux)
        ROOT_DEFAULT="${XDG_DATA_HOME:-$HOME/.local/share}/meridian-loom"
        LICENCE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/meridian-loom/licence" ;;
    Darwin)
        ROOT_DEFAULT="$HOME/Library/Application Support/MeridianLoom"
        LICENCE_DIR="$HOME/Library/Application Support/MeridianLoom/licence" ;;
    *) echo "unsupported operating system (Windows uses uninstall.ps1)" >&2; exit 1 ;;
esac
ROOT=${PREFIX:-$ROOT_DEFAULT}

echo "Meridian Loom uninstall"
found=0
if [ "$NO_EXTENSION" -eq 0 ]; then echo "  - VS Code extension $EXTENSION_ID"; found=1; fi
if [ -d "$ROOT" ]; then echo "  - folder $ROOT  (runtime, sidecar, meridian command)"; found=1; fi
if [ "$PURGE_LICENCE" -eq 1 ] && [ -d "$LICENCE_DIR" ]; then echo "  - licence files in $LICENCE_DIR"; found=1; fi
[ "$found" -eq 1 ] || { echo "Nothing to remove."; exit 0; }
echo "  (your recorded evidence in each workspace .meridian folder is kept)"

if [ "$YES" -ne 1 ]; then
    echo
    echo "This was only a list. Re-run with --yes to remove."
    exit 0
fi

if [ "$NO_EXTENSION" -eq 0 ]; then
    code_cmd=""
    if [ -n "$CODE" ]; then code_cmd=$CODE; else
        for candidate in code code-insiders codium; do
            if command -v "$candidate" >/dev/null 2>&1; then code_cmd=$candidate; break; fi
        done
    fi
    if [ -n "$code_cmd" ]; then
        "$code_cmd" --uninstall-extension "$EXTENSION_ID" || true
    else
        echo "VS Code CLI not found; uninstall the extension from the Extensions view."
    fi
fi
if [ -d "$ROOT" ]; then rm -rf "$ROOT"; echo "removed $ROOT"; fi
if [ "$PURGE_LICENCE" -eq 1 ] && [ -d "$LICENCE_DIR" ]; then
    rm -f "$LICENCE_DIR"/*.mlic
    echo "removed licence files from $LICENCE_DIR"
fi
echo "Done. Restart VS Code to finish."
