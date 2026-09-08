"""Authenticated human identity (FR-M20-01; F1 Workstream C task 15).

FR-M20-01: every human action SHALL be attributed to an authenticated
identity — never a free-text name. D9 (closed by this package): the v1
source of human identity is git ``user.name`` / ``user.email``, resolved
behind the :class:`IdentityProvider` interface; enterprise OIDC lands later
behind the same interface.

The assurance level is load-bearing. A git identity is self-asserted
configuration — the resolver labels it ``local`` and it NEVER counts as
``verified``. The future OIDC provider is the only source of ``verified``
assurance. Governance records carry the assurance next to the identity so
downstream consumers (and the F2 evidence gate) can weigh git-attributed
approvals accordingly.

The extension host selects the provider over the handshake (the same
pattern as the ledger signing key): the host can see git config today and
will hold OIDC tokens in SecretStorage later; the sidecar only ever calls
``resolve()`` through the interface. See ``identityProvider`` in
``shared/schema/methods.json`` (HandshakeParams).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

#: FR-M20-01: "local" = self-asserted (git config); "verified" = attested by
#: an enterprise identity provider (OIDC — enterprise tier, not v1). A git
#: identity can never report "verified".
Assurance = Literal["local", "verified"]

#: Config values the provider registry understands (handshake
#: identityProvider). Anything else is an actionable error naming these.
KNOWN_PROVIDERS = ("git", "oidc")

FR_ID = "FR-M20-01"


@dataclass(frozen=True)
class ResolvedIdentity:
    """One authenticated human identity, with its assurance level."""

    id: str
    display_name: str
    email: str
    assurance: Assurance

    def display(self) -> str:
        """The ledger human_actor string (``Name <email>``)."""
        if self.display_name and self.email:
            return f"{self.display_name} <{self.email}>"
        return self.display_name or self.email

    def wire(self) -> dict:
        """The JSON shape recorded next to approvals/halts/ingests."""
        return {
            "id": self.id,
            "displayName": self.display_name,
            "email": self.email,
            "assurance": self.assurance,
        }


class IdentityUnavailableError(Exception):
    """No human identity could be resolved — never record anonymously."""


class IdentityProviderError(Exception):
    """Configuration error: an unknown provider was requested."""


class IdentityProvider(Protocol):
    """The swappable identity seam (D9): v1 git, enterprise OIDC later."""

    def resolve(self) -> ResolvedIdentity: ...


@dataclass(frozen=True)
class StaticIdentityProvider:
    """Tests and injected callers supply the identity directly."""

    value: ResolvedIdentity

    def resolve(self) -> ResolvedIdentity:
        return self.value


class GitIdentityProvider:
    """FR-M20-01 v1: git user.name/user.email in the workspace repository.

    The resolved identity is labelled assurance "local": git config is
    self-asserted and never counts as verified identity.
    """

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

    def resolve(self) -> ResolvedIdentity:
        name = self._config("user.name")
        email = self._config("user.email")
        if not name and not email:
            raise IdentityUnavailableError(
                f"no human identity in {self._repo}: git user.name/user.email "
                "are not configured; anonymous approval is not possible (FR-M12-07)"
            )
        return ResolvedIdentity(
            # The email is the stable id; the display name is presentation.
            id=email or name,
            display_name=name or email,
            email=email,
            assurance="local",
        )


class OidcIdentityProvider:
    """Enterprise OIDC identity — the FR-M20-01 deferred body.

    Implements the interface so the registry and the handshake selection
    work end-to-end, but ``resolve()`` raises: the verified-assurance
    provider is enterprise tier, not v1. The requirement ID rides in the
    message per the protocol for deferred bodies.
    """

    def resolve(self) -> ResolvedIdentity:
        raise NotImplementedError(
            "FR-M20-01 OIDC provider — enterprise tier, not v1"
        )


def provider_from_config(config: str | None, repo: Path) -> IdentityProvider:
    """The provider registry: select by config, default git, fail closed.

    An unknown config is an actionable error naming the valid choices —
    never a silent fallback to a weaker identity source.
    """
    if config is None or not str(config).strip():
        return GitIdentityProvider(repo)
    name = str(config).strip().lower()
    if name == "git":
        return GitIdentityProvider(repo)
    if name == "oidc":
        return OidcIdentityProvider()
    raise IdentityProviderError(
        f"unknown identity provider '{config}' (FR-M20-01): valid providers "
        f"are {', '.join(KNOWN_PROVIDERS)}; check the meridian.identityProvider "
        "setting and the sidecar version"
    )
