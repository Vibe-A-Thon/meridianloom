"""Where licence files live, and installing and removing them.

Two scopes, so both purchase models have a natural home:

======== ==================================== ===========================================
scope    for                                  location
======== ==================================== ===========================================
user     a per-developer licence              Windows  ``%APPDATA%\\MeridianLoom\\licence``
                                              macOS    ``~/Library/Application Support/MeridianLoom/licence``
                                              Linux    ``$XDG_CONFIG_HOME/meridian-loom/licence``
machine  a per-machine licence, or a          Windows  ``%PROGRAMDATA%\\MeridianLoom\\licence``
         licence an administrator deploys     macOS    ``/Library/Application Support/MeridianLoom/licence``
         for every account on the host        Linux    ``/etc/meridian-loom/licence``
======== ==================================== ===========================================

``MERIDIAN_LICENCE_FILE`` (one file) and ``MERIDIAN_LICENCE_DIR`` (replaces the
user directory) exist for CI images and containers where the OS conventions do
not apply. They are not a bypass: a file they point at still has to carry a
valid signature from a trusted key, exactly like any other.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

LICENCE_SUFFIX = ".mlic"
ENV_LICENCE_FILE = "MERIDIAN_LICENCE_FILE"
ENV_LICENCE_DIR = "MERIDIAN_LICENCE_DIR"
ENV_LICENCE_MACHINE_DIR = "MERIDIAN_LICENCE_MACHINE_DIR"

SCOPE_USER = "user"
SCOPE_MACHINE = "machine"
SCOPES = (SCOPE_USER, SCOPE_MACHINE)


def user_licence_dir() -> Path:
    override = os.environ.get(ENV_LICENCE_DIR)
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "MeridianLoom" / "licence"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MeridianLoom" / "licence"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "meridian-loom" / "licence"


def machine_licence_dir() -> Path:
    override = os.environ.get(ENV_LICENCE_MACHINE_DIR)
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        return Path(base) / "MeridianLoom" / "licence"
    if sys.platform == "darwin":
        return Path("/Library/Application Support/MeridianLoom/licence")
    return Path("/etc/meridian-loom/licence")


def scope_dir(scope: str, user_dir: Path | None = None, machine_dir: Path | None = None) -> Path:
    if scope == SCOPE_USER:
        return user_dir or user_licence_dir()
    if scope == SCOPE_MACHINE:
        return machine_dir or machine_licence_dir()
    raise ValueError(f"unknown licence scope {scope!r}; expected one of {', '.join(SCOPES)}")


def candidate_files(user_dir: Path | None = None, machine_dir: Path | None = None) -> list[Path]:
    """Every file that might be a licence, most specific first: the explicit
    file, then the user's directory, then the machine-wide directory."""
    found: list[Path] = []
    explicit = os.environ.get(ENV_LICENCE_FILE)
    if explicit:
        found.append(Path(explicit))
    for directory in (user_dir or user_licence_dir(), machine_dir or machine_licence_dir()):
        try:
            found.extend(sorted(p for p in directory.iterdir() if p.suffix == LICENCE_SUFFIX and p.is_file()))
        except OSError:
            continue
    return found


def safe_name(licence_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", licence_id).strip("._") or "licence"
    return cleaned[:80] + LICENCE_SUFFIX


def write_licence(text: str, licence_id: str, directory: Path) -> Path:
    """Atomically write a licence into ``directory``."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe_name(licence_id)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)
    except PermissionError as error:
        raise PermissionError(
            f"cannot write to {directory}: {error.strerror or error}. "
            "A machine-wide licence needs administrator (or root) rights; "
            "install with scope 'user' instead, or re-run elevated."
        ) from error
    return target


def remove_licences(directory: Path) -> list[Path]:
    removed: list[Path] = []
    try:
        candidates = [p for p in directory.iterdir() if p.suffix == LICENCE_SUFFIX and p.is_file()]
    except OSError:
        return removed
    for path in candidates:
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            continue
    return removed
