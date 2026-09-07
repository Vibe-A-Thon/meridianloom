"""Human identity for governance (D9; FR-M12-07 support).

v1 identity is git's ``user.name`` / ``user.email`` — the identity a human
already signs commits with. The :class:`IdentityProvider` interface is the
seam workstream C (FR-M20-01) swaps for authenticated identity (OIDC); the
governance surfaces only ever depend on the interface. An unavailable
identity is an error, never a silent anonymous fallback: FR-M12-07 forbids
anonymous approval, so a gate that cannot name its approver refuses rather
than records.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class HumanIdentity:
    name: str
    email: str

    def display(self) -> str:
        if self.name and self.email:
            return f"{self.name} <{self.email}>"
        return self.name or self.email


class IdentityUnavailableError(Exception):
    """No human identity could be resolved — never record anonymously."""


class IdentityProvider(Protocol):
    """The swappable identity seam (D9; OIDC lands behind this in workstream C)."""

    def identity(self) -> HumanIdentity: ...


@dataclass(frozen=True)
class StaticIdentityProvider:
    """Tests and injected callers supply the identity directly."""

    value: HumanIdentity

    def identity(self) -> HumanIdentity:
        return self.value


class GitIdentityProvider:
    """D9 v1: git user.name/user.email in the workspace repository."""

    def __init__(self, repo: Path) -> None:
        self._repo = Path(repo)

    def _config(self, key: str) -> str:
        result = subprocess.run(
            ["git", "config", "--get", key],
            cwd=self._repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def identity(self) -> HumanIdentity:
        name = self._config("user.name")
        email = self._config("user.email")
        if not name and not email:
            raise IdentityUnavailableError(
                f"no human identity in {self._repo}: git user.name/user.email "
                "are not configured; anonymous approval is not possible (FR-M12-07)"
            )
        return HumanIdentity(name=name, email=email)
