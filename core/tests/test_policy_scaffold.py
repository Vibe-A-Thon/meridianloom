"""Fresh-workspace policy bootstrap (D43; AC-53; N0-T09b–T09e).

Proves the uniform fresh-workspace contract for EVERY sidecar-loaded pack
— a new pack cannot land with a fourth behaviour without failing here:

* absent everywhere → the sidecar scaffolds the shipped default into
  ``<ws>/.meridian/policy/`` and reports it (health.policyScaffolds);
* a second bootstrap is a no-op — team edits are never overwritten;
* workspace packs (``.meridian/policy/`` and ``policy/``) always win;
* present-but-invalid fails closed per pack, naming the file, the
  violation, and the remedy (NFR-10; T09e);
* the licenses map resolves the same override chain as the other packs
  (T09c).

Zero model calls (FR-M36-07): filesystem copies and YAML parsing only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.engine.catalogue import load_catalogue
from meridian_core.engine.classify import default_license_map_paths, load_license_map
from meridian_core.governance import bootstrap
from meridian_core.governance.policy import load_policy_pack
from meridian_core.governance.roles import load_role_pack
from meridian_core.metrics.pricing import load_pricing_pack
from meridian_core.metrics.spendfeed import load_story_metadata
from meridian_core.rejection import taxonomy
from meridian_core.server import SidecarServer

SHIPPED = bootstrap.shipped_policy_dir()

BROKEN_YAML = "version: [not-a-mapping"


def _chain(workspace: Path, filename: str) -> list[Path]:
    return [workspace / ".meridian" / "policy" / filename, workspace / "policy" / filename]


def _load_pack(workspace: Path, spec: bootstrap.PolicyPackSpec):
    """Load one pack through its workspace chain, exactly as the engine
    does after a handshake. The taxonomy loader raises instead of
    returning a fail-closed pack, so it is handled by its caller."""
    if spec.key == "governance":
        return load_policy_pack(_chain(workspace, spec.filename))
    if spec.key == "action-classes":
        return load_catalogue(_chain(workspace, spec.filename))
    if spec.key == "roles":
        return load_role_pack(_chain(workspace, spec.filename))
    if spec.key == "pricing":
        return load_pricing_pack(_chain(workspace, spec.filename))
    if spec.key == "stories":
        return load_story_metadata(_chain(workspace, spec.filename))
    if spec.key == "licenses":
        return load_license_map(default_license_map_paths(workspace))
    raise AssertionError(f"no chain loader wired for pack {spec.key}")


# -- T09d: the fresh-workspace scaffold ----------------------------------------


class TestFreshWorkspaceBootstrap:
    def test_every_pack_scaffolds_into_meridian_policy(self, tmp_path: Path):
        events = bootstrap.bootstrap_policy_packs(tmp_path)
        assert {event.pack for event in events} == {
            spec.key for spec in bootstrap.POLICY_PACKS
        }
        for spec in bootstrap.POLICY_PACKS:
            (event,) = [event for event in events if event.pack == spec.key]
            assert event.action == "scaffolded", event.message
            destination = tmp_path / ".meridian" / "policy" / spec.filename
            assert event.path == str(destination)
            assert destination.is_file()
            # The scaffold is a byte copy of the shipped default, so the
            # workspace starts from exactly the reviewed policy.
            assert destination.read_bytes() == (SHIPPED / spec.filename).read_bytes()

    def test_every_scaffolded_pack_parses_valid(self, tmp_path: Path):
        bootstrap.bootstrap_policy_packs(tmp_path)
        for spec in bootstrap.POLICY_PACKS:
            if spec.key == "rework-reasons":
                continue  # raise-style loader, asserted below
            pack = _load_pack(tmp_path, spec)
            assert not pack.fail_closed, f"{spec.key}: {pack.errors}"
        # The taxonomy loader (raise-style fail-closed) parses too.
        loaded = taxonomy.load_taxonomy(taxonomy.default_taxonomy_paths(tmp_path))
        assert loaded.source == str(tmp_path / ".meridian" / "policy" / "rework-reasons.yaml")

    def test_second_bootstrap_is_a_noop_and_never_overwrites_team_edits(
        self, tmp_path: Path
    ):
        bootstrap.bootstrap_policy_packs(tmp_path)
        edited = tmp_path / ".meridian" / "policy" / "pricing.yaml"
        team_version = "# team-owned rate card\n" + edited.read_text(encoding="utf-8")
        edited.write_text(team_version, encoding="utf-8")

        second = bootstrap.bootstrap_policy_packs(tmp_path)

        # Nothing overwritten, everything reported as already present.
        assert edited.read_text(encoding="utf-8") == team_version
        for event in second:
            assert event.action == "present", event.message
            assert event.path is not None
        # And no second copy appears beside a workspace-policy/ pack.
        assert not (tmp_path / "policy").exists() or not any(
            (tmp_path / "policy").glob("*.yaml")
        )

    def test_workspace_policy_dir_wins_over_scaffold(self, tmp_path: Path):
        team_pack = tmp_path / "policy" / "stories.yaml"
        team_pack.parent.mkdir(parents=True)
        team_pack.write_text(
            "version: 1\nstories:\n  S-1:\n    team: payments\n    costCentre: CC-9\n",
            encoding="utf-8",
        )
        events = bootstrap.bootstrap_policy_packs(tmp_path)
        (event,) = [event for event in events if event.pack == "stories"]
        assert event.action == "present"
        assert event.path == str(team_pack)
        # No .meridian copy is made when a workspace pack already exists.
        assert not (tmp_path / ".meridian" / "policy" / "stories.yaml").exists()

    def test_existing_meridian_pack_is_never_overwritten(self, tmp_path: Path):
        target = tmp_path / ".meridian" / "policy" / "governance.yaml"
        target.parent.mkdir(parents=True)
        target.write_text(
            "version: 1\nprotectedBranches: [main]\n", encoding="utf-8"
        )
        events = bootstrap.bootstrap_policy_packs(tmp_path)
        (event,) = [event for event in events if event.pack == "governance"]
        assert event.action == "present"
        assert target.read_text(encoding="utf-8") == "version: 1\nprotectedBranches: [main]\n"

    def test_scaffold_warnings_only_report_what_happened(self, tmp_path: Path):
        first = bootstrap.bootstrap_policy_packs(tmp_path)
        warnings = bootstrap.scaffold_warnings(first)
        assert len(warnings) == len(bootstrap.POLICY_PACKS)  # all scaffolded
        assert all("scaffolded" in warning for warning in warnings)
        second = bootstrap.bootstrap_policy_packs(tmp_path)
        assert bootstrap.scaffold_warnings(second) == []  # all present: silent


# -- T09e: present-but-invalid fails closed per pack ----------------------------

# The taxonomy loader raises instead of returning a fail-closed pack, so
# it is covered by its own test below.


class TestPresentButInvalidFailsClosed:
    @pytest.mark.parametrize(
        "pack_key",
        tuple(spec.key for spec in bootstrap.POLICY_PACKS if spec.key != "rework-reasons"),
    )
    def test_invalid_workspace_pack_fails_closed_naming_file_and_remedy(
        self, tmp_path: Path, pack_key: str
    ):
        (spec,) = [spec for spec in bootstrap.POLICY_PACKS if spec.key == pack_key]
        broken = tmp_path / ".meridian" / "policy" / spec.filename
        broken.parent.mkdir(parents=True)
        broken.write_text(BROKEN_YAML, encoding="utf-8")

        pack = _load_pack(tmp_path, spec)

        assert pack.fail_closed
        assert any(str(broken) in error for error in pack.errors)
        assert any(bootstrap.FAIL_CLOSED_REMEDY in error for error in pack.errors)

    def test_invalid_taxonomy_raises_naming_file_and_remedy(self, tmp_path: Path):
        broken = tmp_path / ".meridian" / "policy" / "rework-reasons.yaml"
        broken.parent.mkdir(parents=True)
        broken.write_text(BROKEN_YAML, encoding="utf-8")
        with pytest.raises(taxonomy.TaxonomyError) as error:
            taxonomy.load_taxonomy(taxonomy.default_taxonomy_paths(tmp_path))
        assert str(broken) in str(error.value)
        assert bootstrap.FAIL_CLOSED_REMEDY in str(error.value)

    @pytest.mark.parametrize("pack_key", ("governance", "action-classes"))
    def test_absent_fail_closed_pack_names_remedy(self, pack_key: str):
        # The loaders' own last-resort path (no workspace bootstrap ran):
        # a fail-closed pack names the remedy, not just the paths tried.
        (spec,) = [spec for spec in bootstrap.POLICY_PACKS if spec.key == pack_key]
        nowhere = Path("/nonexistent-workspace")
        pack = _load_pack(nowhere, spec)
        assert pack.fail_closed
        assert any("Remedy" in error for error in pack.errors)

    @pytest.mark.parametrize("pack_key", ("roles", "pricing", "stories"))
    def test_absent_tolerant_pack_uses_documented_fallback(self, pack_key: str):
        # The tolerant packs keep their documented defensive last resorts
        # when no bootstrap ran: roles' built-in default, an empty pricing
        # pack, an empty story pack — never an exception, never fabricated.
        (spec,) = [spec for spec in bootstrap.POLICY_PACKS if spec.key == pack_key]
        pack = _load_pack(Path("/nonexistent-workspace"), spec)
        assert not pack.fail_closed

    def test_absent_license_map_falls_through_to_shipped_default(self):
        # With no workspace pack the chain lands on the shipped default —
        # in a packaged extension this file always exists because
        # package-extension.mjs copies every policy pack into the VSIX.
        pack = load_license_map(
            default_license_map_paths(Path("/nonexistent-workspace"))
        )
        assert not pack.fail_closed
        assert pack.source == str(bootstrap.shipped_policy_dir() / "licenses.yaml")


# -- T09c: the licenses override chain -------------------------------------------


class TestLicenseMapOverrideChain:
    def test_chain_order_meridian_then_workspace_policy_then_shipped(
        self, tmp_path: Path
    ):
        meridian = tmp_path / ".meridian" / "policy" / "licenses.yaml"
        meridian.parent.mkdir(parents=True)
        meridian.write_text("version: 1\nlicenses:\n  dep: MIT\n", encoding="utf-8")
        workspace = tmp_path / "policy" / "licenses.yaml"
        workspace.parent.mkdir(parents=True)
        workspace.write_text("version: 1\nlicenses:\n  dep: Apache-2.0\n", encoding="utf-8")

        chain = default_license_map_paths(tmp_path)
        assert chain == [meridian, workspace, bootstrap.shipped_policy_dir() / "licenses.yaml"]
        pack = load_license_map(chain)
        assert not pack.fail_closed
        assert pack.lookup("dep") == "MIT"  # .meridian/policy wins

    def test_workspace_policy_dir_used_when_no_meridian_override(self, tmp_path: Path):
        workspace = tmp_path / "policy" / "licenses.yaml"
        workspace.parent.mkdir(parents=True)
        workspace.write_text("version: 1\nlicenses:\n  dep: BSD-3-Clause\n", encoding="utf-8")
        pack = load_license_map(default_license_map_paths(tmp_path))
        assert pack.lookup("dep") == "BSD-3-Clause"

    def test_shipped_default_used_when_no_workspace_pack(self, tmp_path: Path):
        pack = load_license_map(default_license_map_paths(tmp_path))
        assert not pack.fail_closed
        assert pack.source == str(bootstrap.shipped_policy_dir() / "licenses.yaml")

    def test_empty_chain_fails_closed_naming_remedy(self, tmp_path: Path):
        pack = load_license_map(
            [
                tmp_path / ".meridian" / "policy" / "licenses.yaml",
                tmp_path / "policy" / "licenses.yaml",
            ]
        )
        assert pack.fail_closed
        assert any("Remedy" in error for error in pack.errors)


# -- scaffold reporting reaches the host -----------------------------------------


class TestScaffoldReporting:
    def _handshake(self, server: SidecarServer, workspace: Path) -> dict:
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "pytest",
                    "tiers": ["flight-recorder", "governor"],
                    "workspaceDir": str(workspace),
                },
            }
        )
        assert "result" in response, response
        return response["result"]

    def test_health_reports_scaffold_events(self, tmp_path: Path):
        server = SidecarServer()
        self._handshake(server, tmp_path / "workspace")
        response = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "health"})
        result = response["result"]
        scaffolds = result["policyScaffolds"]
        assert {event["pack"] for event in scaffolds} == {
            spec.key for spec in bootstrap.POLICY_PACKS
        }
        assert all(event["action"] == "scaffolded" for event in scaffolds)
        assert all(event["path"] for event in scaffolds)
        assert all("scaffolded" in event["message"] for event in scaffolds)

    def test_second_handshake_reports_present_no_overwrite(self, tmp_path: Path):
        workspace = tmp_path / "workspace"
        server = SidecarServer()
        self._handshake(server, workspace)
        edited = workspace / ".meridian" / "policy" / "roles.yaml"
        team_version = "# team role pack\n" + edited.read_text(encoding="utf-8")
        edited.write_text(team_version, encoding="utf-8")

        self._handshake(server, workspace)
        response = server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "health"})

        assert edited.read_text(encoding="utf-8") == team_version
        assert all(
            event["action"] == "present" for event in response["result"]["policyScaffolds"]
        )

    def test_health_before_handshake_has_no_scaffolds(self):
        server = SidecarServer()
        response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "health"})
        assert response["result"]["policyScaffolds"] == []
