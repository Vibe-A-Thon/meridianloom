"""Authenticated identity (FR-M20-01; F1 Workstream C task 15).

FR-M20-01: every human action SHALL be attributed to an authenticated
identity, never a free-text name. D9 (closed here): v1 identity is git
user.name/user.email behind an IdentityProvider interface; enterprise OIDC
is a stub. The load-bearing rule: a git identity resolves with assurance
"asserted" (D38's recorded level name) — it is what a human typed into git
config, not proof of anything — and a git identity NEVER counts as
"verified". That distinction is what the later enterprise OIDC provider
plugs into.

* GitIdentityProvider resolves git user.name/user.email from the workspace
  repository, labelled assurance "asserted";
* OidcIdentityProvider is a contracted stub: it implements the interface
  but raises NotImplementedError carrying the FR id (per the protocol for
  deferred bodies);
* the provider registry selects by config; an unknown config is an
  actionable error naming the valid choices;
* the server resolves the approver/halting/ingesting identity from the
  provider — never a raw string param (gate.approve, gate.halt, pr/ingest);
* the handshake selects the provider (default git), so the extension host
  owns the choice it can later back with SecretStorage OIDC tokens.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.identity import (
    GitIdentityProvider,
    IdentityProviderError,
    IdentityUnavailableError,
    OidcIdentityProvider,
    ResolvedIdentity,
    StaticIdentityProvider,
    provider_from_config,
)
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed:\n{result.stderr}"
    return result.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    target.mkdir()
    git(target, "init")
    git(target, "config", "user.name", "Ada Lovelace")
    git(target, "config", "user.email", "ada@example.com")
    return target


class TestGitIdentityProvider:
    def test_resolves_git_config_identity(self, repo: Path) -> None:
        identity = GitIdentityProvider(repo).resolve()
        assert identity.display_name == "Ada Lovelace"
        assert identity.email == "ada@example.com"
        assert identity.id == "ada@example.com"

    def test_assurance_is_asserted_never_verified(self, repo: Path) -> None:
        # The asserted/verified distinction is load-bearing (D9, D38): git
        # config is self-asserted, so it must never be reported as verified
        # identity.
        identity = GitIdentityProvider(repo).resolve()
        assert identity.assurance == "asserted"
        assert identity.assurance != "verified"

    def test_missing_identity_is_a_refusal_not_a_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Isolate from the developer's global git identity: with no git
        # config anywhere, resolving must refuse — never fall back to
        # anonymous.
        empty_global = tmp_path / "empty-gitconfig"
        empty_global.write_text("", encoding="utf-8")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_global))
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        bare = tmp_path / "bare"
        bare.mkdir()
        git(bare, "init")
        with pytest.raises(IdentityUnavailableError, match="FR-M12-07"):
            GitIdentityProvider(bare).resolve()


class TestOidcIdentityProviderStub:
    def test_resolve_raises_with_requirement_id(self) -> None:
        provider = OidcIdentityProvider()
        with pytest.raises(NotImplementedError, match="FR-M20-01"):
            provider.resolve()

    def test_stub_message_names_enterprise_tier(self) -> None:
        try:
            OidcIdentityProvider().resolve()
        except NotImplementedError as error:
            assert "OIDC" in str(error)
        else:  # pragma: no cover - the stub must never silently resolve
            pytest.fail("OIDC stub resolved an identity instead of raising")


class TestProviderRegistry:
    def test_git_config_selects_git_provider(self, repo: Path) -> None:
        provider = provider_from_config("git", repo)
        assert isinstance(provider, GitIdentityProvider)
        assert provider.resolve().display_name == "Ada Lovelace"

    def test_oidc_config_selects_the_stub(self, repo: Path) -> None:
        provider = provider_from_config("oidc", repo)
        assert isinstance(provider, OidcIdentityProvider)
        with pytest.raises(NotImplementedError, match="FR-M20-01"):
            provider.resolve()

    def test_unknown_config_is_an_actionable_error(self, repo: Path) -> None:
        with pytest.raises(IdentityProviderError) as caught:
            provider_from_config("sso-via-ldap", repo)
        message = str(caught.value)
        assert "sso-via-ldap" in message
        assert "git" in message and "oidc" in message

    def test_default_is_git(self, repo: Path) -> None:
        assert isinstance(provider_from_config(None, repo), GitIdentityProvider)


class TestIdentityStaticProvider:
    def test_static_provider_for_injected_callers(self) -> None:
        value = ResolvedIdentity(
            id="grace@example.com",
            display_name="Grace Hopper",
            email="grace@example.com",
            assurance="verified",
        )
        assert StaticIdentityProvider(value).resolve() is value


def _server(tmp_path: Path, repo: Path, identity: ResolvedIdentity) -> SidecarServer:
    server = SidecarServer(
        ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider()),
        identity_provider=StaticIdentityProvider(identity),
    )
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "test",
                "tiers": ["flight-recorder", "governor"],
                "workspaceDir": str(repo),
            },
        }
    )
    return server


def _request(server: SidecarServer, request_id: int, method: str, params: dict) -> dict:
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


GRACE = ResolvedIdentity(
    id="grace@example.com",
    display_name="Grace Hopper",
    email="grace@example.com",
    assurance="asserted",
)


class TestProviderResolvedApprovals:
    """The approver/halting identity comes from the provider, not a param."""

    def test_gate_approve_records_provider_identity(
        self, tmp_path: Path, repo: Path
    ) -> None:
        server = _server(tmp_path, repo, GRACE)
        response = _request(
            server,
            2,
            "gate.approve",
            {"subject": "main", "commit": "abc123", "role": "approver"},
        )
        assert "error" not in response, response
        result = response["result"]
        assert result["recorded"] is True
        assert result["approver"] == {
            "name": "Grace Hopper",
            "email": "grace@example.com",
        }
        ledger = server.ledger
        rows = ledger.query(action_type="approval", limit=10)
        assert len(rows) == 1
        assert rows[0]["human_actor"] == "Grace Hopper <grace@example.com>"
        detail = _read_detail(ledger, rows[0])
        assert detail["approver"] == {
            "id": "grace@example.com",
            "displayName": "Grace Hopper",
            "email": "grace@example.com",
            "assurance": "asserted",
        }

    def test_gate_halt_records_provider_identity(
        self, tmp_path: Path, repo: Path
    ) -> None:
        server = _server(tmp_path, repo, GRACE)
        response = _request(
            server,
            2,
            "gate.halt",
            {"reason": "security incident", "scope": "merge", "subject": "main"},
        )
        assert "error" not in response, response
        rows = [
            row
            for row in server.ledger.query(action_type="gate", limit=10)
            if row.get("decision") == "halted"
        ]
        assert len(rows) == 1
        assert rows[0]["human_actor"] == "Grace Hopper <grace@example.com>"
        assert _read_detail(server.ledger, rows[0])["haltedBy"] == {
            "id": "grace@example.com",
            "displayName": "Grace Hopper",
            "email": "grace@example.com",
            "assurance": "asserted",
        }

    def test_pr_ingest_records_the_ingesting_identity(
        self, tmp_path: Path, repo: Path
    ) -> None:
        import json

        fixture = Path(__file__).parent / "fixtures" / "gh_api" / "pull_41_detail.json"
        server = _server(tmp_path, repo, GRACE)
        response = _request(
            server,
            2,
            "pr/ingest",
            {"pr": json.loads(fixture.read_text(encoding="utf-8"))},
        )
        assert "error" not in response, response
        result = response["result"]
        assert result["ingestedBy"] == {
            "name": "Grace Hopper",
            "email": "grace@example.com",
            "assurance": "asserted",
        }
        ledger = server.ledger
        rows = ledger.query(action_type="pr_ingest", limit=10)
        assert len(rows) == 1
        assert rows[0]["human_actor"] == "Grace Hopper <grace@example.com>"
        detail = _read_detail(ledger, rows[0])
        assert detail["ingestedBy"]["id"] == "grace@example.com"


def _read_detail(ledger: Ledger, row: dict) -> dict:
    import json

    return json.loads(ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8"))


class TestHandshakeProviderSelection:
    def test_handshake_selects_oidc_provider(self, tmp_path: Path, repo: Path) -> None:
        server = SidecarServer(
            ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "test",
                    "tiers": ["flight-recorder", "governor"],
                    "workspaceDir": str(repo),
                    "identityProvider": "oidc",
                },
            }
        )
        assert "error" not in response, response
        # The provider is selected at the handshake; resolving through it is
        # the enterprise-tier stub's refusal, with the FR id.
        denied = _request(
            server, 2, "gate.approve", {"subject": "main", "commit": "abc"}
        )
        assert denied["error"]["code"] == protocol.INVALID_PARAMS
        assert "FR-M20-01" in denied["error"]["message"]

    def test_unknown_handshake_provider_is_actionable(
        self, tmp_path: Path, repo: Path
    ) -> None:
        server = SidecarServer(
            ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        )
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "test",
                    "workspaceDir": str(repo),
                    "identityProvider": "ldap",
                },
            }
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert "ldap" in response["error"]["message"]
        assert "git" in response["error"]["message"]

    def test_workspace_git_provider_is_the_default(
        self, tmp_path: Path, repo: Path
    ) -> None:
        """No handshake selection and no injection: the workspace's git
        config resolves — the existing D9 behaviour, now with assurance."""
        server = SidecarServer(
            ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        )
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "test",
                    "tiers": ["flight-recorder", "governor"],
                    "workspaceDir": str(repo),
                },
            }
        )
        approved = _request(
            server, 2, "gate.approve", {"subject": "main", "commit": "abc"}
        )
        assert "error" not in approved, approved
        assert approved["result"]["approver"] == {
            "name": "Ada Lovelace",
            "email": "ada@example.com",
        }


def test_identity_module_has_no_model_calls() -> None:
    """FR-M36-07: the identity package is scanner-clean by construction."""
    from test_no_model_calls import find_violations

    package = Path(__file__).resolve().parent.parent / "meridian_core" / "identity"
    assert find_violations(package) == []
