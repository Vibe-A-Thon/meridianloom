"""The machine fingerprint a per-machine licence is bound to.

The fingerprint is a salted SHA-256 of the operating system's own machine
identifier, formatted ``MLM1-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX``. It is one-way:
the raw identifier is never stored, logged or shown, and the fingerprint is
only ever displayed to the person who asked for it so they can send it to
their Meridian Loom licence contact. Nothing here touches the network.

Sources, in order of preference:

* Windows — ``HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid``
* macOS   — ``IOPlatformUUID`` from ``ioreg``
* Linux   — ``/etc/machine-id`` (then ``/var/lib/dbus/machine-id``)

Two honest limitations, both stated in ``LICENSING.md``:

* **Cloned images share an id.** A VM or container image cloned without
  regenerating its machine id yields the same fingerprint on every clone.
  Per-machine licences are for real workstations, servers and long-lived VMs;
  ephemeral build agents need a different arrangement (contact the licensor).
* **Remote development.** Under VS Code Remote the sidecar runs on the remote
  host, so the fingerprint is the remote host's, which is the machine that is
  actually running the software.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

from ..childenv import child_environment

_SALT = "meridian-loom|machine|v1|"
_LINUX_IDS = ("/etc/machine-id", "/var/lib/dbus/machine-id")


def _windows_machine_guid() -> str | None:
    try:
        import winreg  # type: ignore[import-not-found]

        # KEY_WOW64_64KEY: a 32-bit Python on 64-bit Windows would otherwise
        # read the redirected 32-bit view, which has no MachineGuid.
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip() or None
    except OSError:
        return None


def _macos_platform_uuid() -> str | None:
    try:
        completed = subprocess.run(
            ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=5,
            env=child_environment(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', completed.stdout or "")
    return match.group(1).strip() if match else None


def _linux_machine_id() -> str | None:
    for candidate in _LINUX_IDS:
        try:
            value = Path(candidate).read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if value:
            return value
    return None


def raw_machine_id() -> str | None:
    """The OS identifier, or None when this system offers none."""
    if sys.platform == "win32":
        return _windows_machine_guid()
    if sys.platform == "darwin":
        return _macos_platform_uuid()
    return _linux_machine_id()


def fingerprint_for(machine_id: str) -> str:
    digest = hashlib.sha256((_SALT + machine_id.strip().lower()).encode("utf-8")).hexdigest().upper()
    groups = [digest[i : i + 5] for i in range(0, 25, 5)]
    return "MLM1-" + "-".join(groups)


def machine_fingerprint() -> str | None:
    """This machine's fingerprint, or None if it cannot be determined (in
    which case a per-machine licence cannot be verified here and the
    per-developer kind is the alternative)."""
    identifier = raw_machine_id()
    return fingerprint_for(identifier) if identifier else None
