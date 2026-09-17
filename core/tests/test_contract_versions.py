"""FR-M44-06/07, NFR-40 (N2 Workstream E task 24): the external contract
version is recorded on every derived ledger entry — resolved from the pin
manifest, and visibly degraded (never silent, never invented) when a
source has no pin.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core import contract_versions as cv
from meridian_core import protocol
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer

from test_attribution import git
from test_interop_rpc import write_note


@pytest.fixture()
def manifest() -> dict:
    return cv.load_manifest()


# -- resolver unit contract --------------------------------------------------


def test_observer_vendor_resolves_to_pinned_adapter_version(manifest) -> None:
    version = cv.resolve_source_version("cursor", manifest)
    assert version is not None
    assert version.startswith("observer-adapter/")


def test_named_contract_resolves_to_pinned_version(manifest) -> None:
    version = cv.resolve_source_version("acp-protocol", manifest)
    assert version == "contract/acp-protocol/0.4.5"


def test_unpinned_source_returns_none_never_a_version(manifest) -> None:
    assert cv.resolve_source_version("aider", manifest) is None
    assert cv.resolve_source_version("unknown-tool", manifest) is None


def test_stamp_records_version(manifest) -> None:
    detail, version = cv.stamp_external_contract({"digest": "x"}, "cursor", manifest)
    assert detail["externalContractVersion"] == version
    assert version is not cv.UNPINNED


def test_stamp_records_unpinned_visibly(manifest) -> None:
    detail, version = cv.stamp_external_contract({"digest": "x"}, "aider", manifest)
    assert version == cv.UNPINNED
    assert detail["externalContractVersion"] == "unpinned"


def test_stamp_never_drops_existing_detail(manifest) -> None:
    detail, _ = cv.stamp_external_contract({"digest": "x", "keep": 1}, "cursor", manifest)
    assert detail["keep"] == 1


# -- derived ledger entries carry the version (real server + ledger) ---------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "commit.gpgsign", "false")
    (root / "app.txt").write_text("hello\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    return root


def make_server(repo: Path, tmp_path: Path) -> SidecarServer:
    instance = SidecarServer(
        ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    )
    instance.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "pytest",
                "workspaceDir": str(repo),
                "tiers": ["flight-recorder"],
            },
        }
    )
    return instance


def call(server: SidecarServer, method: str, params: dict | None = None) -> dict:
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 9, "method": method, "params": params or {}}
    )
    assert "error" not in response, response.get("error")
    return response["result"]


def notarised_details(server: SidecarServer) -> list[dict]:
    ledger = server._ensure_ledger()
    details = []
    for row in ledger.query(action_type="foreign_record_notarised", limit=100):
        blob = ledger.read_blob(row["input_ref"], row["blob_key_id"])
        details.append(json.loads(blob.decode("utf-8")))
    return details


def test_notarised_entry_records_pinned_contract_version(repo: Path, tmp_path: Path) -> None:
    head = git(repo, "rev-parse", "HEAD").strip()
    write_note(repo, "refs/notes/cursor", head, json.dumps({"tool": "cursor"}))
    server = make_server(repo, tmp_path)

    result = call(server, "interop/notarise")

    assert result["notarised"] == 1
    assert result["unpinnedContracts"] == []
    details = notarised_details(server)
    assert len(details) == 1
    assert details[0]["externalContractVersion"].startswith("observer-adapter/")


def test_notarised_entry_degrades_visibly_when_unpinned(
    repo: Path, tmp_path: Path
) -> None:
    head = git(repo, "rev-parse", "HEAD").strip()
    write_note(repo, "refs/notes/aider", head, json.dumps({"tool": "aider"}))
    server = make_server(repo, tmp_path)

    result = call(server, "interop/notarise")

    assert result["unpinnedContracts"] == ["aider"]
    details = notarised_details(server)
    assert details[0]["externalContractVersion"] == "unpinned"
