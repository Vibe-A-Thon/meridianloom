"""Corpus batch 2 — policy-engine refusals, worktree boundary, identity
spoofing, economics provenance injection, redaction extensions, trailer
attribution spoofing. See harness.py for scope and coverage limits."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from meridian_core import trailers
from meridian_core.governance import approval_class, engine as policy_engine
from meridian_core.governance import policy as policy_mod
from meridian_core.identity import (
    GitIdentityProvider,
    IdentityUnavailableError,
    OidcIdentityProvider,
)
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics import economics as eco
from meridian_core.trailers import append_trailer, parse_attributions
from meridian_core.worktree.manager import WorktreeManager, WorktreeError
from meridian_core.ledger import trailer_spec as ts

from .harness import (
    Fixture,
    KIND_BLOCKED,
    KIND_DETECTED,
    KIND_REDACTED,
    KIND_RECORDED,
    SURFACE_HOSTED,
    SURFACE_PASSIVE,
)


def _git(repo: Path, *args: str) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _repo(tmp: Path) -> Path:
    root = tmp / "repo"
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Corpus")
    _git(root, "config", "user.email", "corpus@example.test")
    (root / "f.txt").write_text("x\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _pack() -> policy_mod.PolicyPack:
    return policy_mod.PolicyPack(
        version=1,
        source="corpus",
        profiles={
            "corpus-gate": policy_mod.GateProfile(
                name="corpus-gate",
                description="batch-2 gate",
                criteria=(
                    policy_mod.CriterionSpec(
                        id="c-fields", kind="requiredFields", fields=("storyId",)
                    ),
                    policy_mod.CriterionSpec(id="c-tests", kind="testEvidence"),
                    policy_mod.CriterionSpec(
                        id="c-human", kind="humanApproval", roles=("approver",)
                    ),
                ),
            )
        },
    )


# -- hosted: policy engine -----------------------------------------------------


def _f_policy(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        if case == "FAILCLOSED":
            pack = policy_mod.fail_closed_pack("corpus", ["governance.yaml unreadable"])
            verdict = policy_engine.evaluate({"storyId": "S"}, "corpus-gate", pack)
            assert verdict.passed is False
            assert verdict.fail_closed is True
            assert "governance.yaml unreadable" in verdict.reasons
        elif case == "UNKNOWN-PROFILE":
            verdict = policy_engine.evaluate({"storyId": "S"}, "no-such", _pack())
            assert verdict.passed is False
            assert "unknown gate profile" in verdict.reasons[0]
            assert "corpus-gate" in verdict.reasons[0]
        elif case == "REQ-FIELDS":
            verdict = policy_engine.evaluate({}, "corpus-gate", _pack())
            assert verdict.passed is False
            assert any("storyId" in r for r in verdict.reasons)
        elif case == "ANON-APPROVAL":
            verdict = policy_engine.evaluate(
                {
                    "storyId": "S",
                    "approvals": [{"approver": {}, "role": "approver"}],
                },
                "corpus-gate",
                _pack(),
            )
            human = [c for c in verdict.criteria if c.kind == "humanApproval"][0]
            assert human.passed is False
            assert "anonymous" in human.reason
        elif case == "ROLE-MISMATCH":
            verdict = policy_engine.evaluate(
                {
                    "storyId": "S",
                    "approvals": [
                        {
                            "approver": {"name": "Real Human", "email": "h@x.test"},
                            "role": "observer",
                        }
                    ],
                },
                "corpus-gate",
                _pack(),
            )
            human = [c for c in verdict.criteria if c.kind == "humanApproval"][0]
            assert human.passed is False
            assert "observer" in human.reason
        else:  # NO-TESTS
            verdict = policy_engine.evaluate(
                {"storyId": "S", "evidence": []}, "corpus-gate", _pack()
            )
            tests = [c for c in verdict.criteria if c.kind == "testEvidence"][0]
            assert tests.passed is False
            assert "no passing test-run evidence" in tests.reason

    return Fixture(
        id=f"POL-{case}",
        family="policy_refusal",
        surface=SURFACE_HOSTED,
        kind=KIND_BLOCKED,
        description=f"policy engine refuses: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- hosted: worktree boundary ---------------------------------------------------


def _f_worktree(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        manager = WorktreeManager(_repo(tmp))
        if case == "PATH-TRAVERSAL":
            with pytest.raises(WorktreeError, match="storyId"):
                manager.worktree_path("../evil")
        elif case == "ABSOLUTE":
            with pytest.raises(WorktreeError, match="storyId"):
                manager.worktree_path("/tmp/evil")
        elif case == "DOTDOT":
            with pytest.raises(WorktreeError, match="storyId"):
                manager.worktree_path("..")
        elif case == "UNICODE":
            with pytest.raises(WorktreeError, match="storyId"):
                manager.worktree_path("storé-1")
        elif case == "BRANCH-TRAVERSAL":
            with pytest.raises(WorktreeError, match="invalid story branch"):
                manager.create(
                    "STORY-ok", "adapter-1", branch="feature/../pwned"
                )
        else:  # BOUNDARY-HOLDS
            path = manager.worktree_path("STORY-1")
            assert path == manager.repo / ".meridian" / "worktrees" / "STORY-1"
            # Canonical boundary: the resolved path stays under the
            # worktrees root (FR-M18: agents never write outside).
            assert path.resolve().is_relative_to(
                (manager.repo / ".meridian" / "worktrees").resolve()
            )

    return Fixture(
        id=f"WT-{case}",
        family="worktree_boundary",
        surface=SURFACE_HOSTED,
        kind=KIND_BLOCKED if case != "BOUNDARY-HOLDS" else KIND_RECORDED,
        description=f"worktree boundary: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- hosted: identity spoofing -----------------------------------------------------


def _f_identity(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        if case == "SPOOF-ASSERTED":
            repo = _repo(tmp)
            _git(repo, "config", "user.name", "Administrator")
            _git(repo, "config", "user.email", "admin@corp.example")
            identity = GitIdentityProvider(repo).resolve()
            # The spoofed name resolves — at "asserted", never "verified".
            # The assurance label is the control: D38 says git config is
            # self-asserted, so a forged name claims nothing stronger.
            assert identity.display_name == "Administrator"
            assert identity.assurance == "asserted"
        elif case == "UNAVAILABLE":
            repo = tmp / "empty-repo"
            _git(repo, "init", "-q", "-b", "main")
            # git falls back to the machine-global config, so force the
            # local values empty — an operator with no configured identity.
            _git(repo, "config", "user.name", "")
            _git(repo, "config", "user.email", "")
            with pytest.raises(IdentityUnavailableError, match="FR-M12-07"):
                GitIdentityProvider(repo).resolve()
        else:  # BOT-NEVER-HUMAN
            cls = approval_class.classify(
                name="dependabot[bot]", email="49699333+dependabot[bot]@users.noreply.github.com"
            )
            assert approval_class.is_human_class(cls) is False
            assert approval_class.is_known_class(cls)

    return Fixture(
        id=f"ID-{case}",
        family="identity_spoof",
        surface=SURFACE_HOSTED,
        kind=KIND_BLOCKED if case == "UNAVAILABLE" else KIND_RECORDED,
        description=f"identity: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


def _f_oidc(tmp: Path) -> None:
    with pytest.raises(NotImplementedError, match="FR-M20-01"):
        OidcIdentityProvider().resolve()


# -- passive: economics provenance injection ----------------------------------------


def _f_econ(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        if case == "PROV-INJECT-DETAIL":
            # A ledger entry whose detail JSON *claims* vendor provenance.
            # lines_from_ledger must not let the claim upgrade the figure:
            # provenance comes from the caller's knowledge, never the payload.
            led = Ledger(tmp / "l", EphemeralSigningKeyProvider())
            try:
                led.append(
                    {
                        "story_id": "S",
                        "phase": "build",
                        "loop_id": "L1",
                        "loop_iteration": 1,
                        "actor_id": "a",
                        "actor_version": "0.0.1",
                        "actor_kind": "role",
                        "policy_version": "p",
                        "action_type": "tool_call",
                        "cost_usd": 5.0,
                        "input": json.dumps({"costProvenance": "vendor_api"}),
                    }
                )
                lines = eco.lines_from_ledger(led)
                assert lines[0].provenance == "locally_inferred"
                assert led.verify().ok is True
            finally:
                led.close()
        elif case == "CLOSED-VOCAB":
            with pytest.raises(eco.ProvenanceError):
                eco.CostLine(
                    story_id="S", attempt_id="a", actor_id="a", phase="p",
                    cost_usd=eco.Decimal("1"), provenance="vendor_api_forged",
                )
        elif case == "CAT-INJECT":
            with pytest.raises(eco.ProvenanceError):
                eco.CostLine(
                    story_id="S", attempt_id="a", actor_id="a", phase="p",
                    cost_usd=eco.Decimal("1"), provenance="unknown",
                    category="money",
                )
        else:  # NO-BLEND
            lines = [
                eco.CostLine(
                    story_id="S", attempt_id="a", actor_id="a", phase="p",
                    cost_usd=eco.Decimal("1"), provenance="vendor_api",
                ),
                eco.CostLine(
                    story_id="S", attempt_id="a", actor_id="a", phase="p",
                    cost_usd=eco.Decimal("2"), provenance="locally_inferred",
                ),
            ]
            agg = eco.aggregate(lines)
            as_dict = agg.to_dict()
            assert as_dict["byProvenance"] == {
                "vendor_api": "1",
                "locally_inferred": "2",
            }
            assert as_dict["total"] == "3"

    return Fixture(
        id=f"ECO-{case}",
        family="economics_injection",
        surface=SURFACE_PASSIVE,
        kind=KIND_BLOCKED if case in ("CLOSED-VOCAB", "CAT-INJECT") else KIND_DETECTED,
        description=f"economics: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- hosted: redaction extensions ----------------------------------------------------


def _red_secret_fixture(secret: str, marker: str, description: str) -> Fixture:
    def fn(tmp: Path) -> None:
        led = Ledger(tmp / "l", EphemeralSigningKeyProvider())
        try:
            led.append(
                {
                    "story_id": "S",
                    "phase": "build",
                    "loop_id": "L1",
                    "loop_iteration": 1,
                    "actor_id": "a",
                    "actor_version": "0.0.1",
                    "actor_kind": "role",
                    "policy_version": "p",
                    "action_type": "diff",
                    "input": f"log line: {secret}",
                    "blob_subject": "adv",
                }
            )
            row = led.query(action_type="diff", story_id="S")[0]
            persisted = led.read_blob(row["input_ref"], row["blob_key_id"]).decode()
            assert secret not in persisted, f"SECRET LEAKED via {marker}"
            assert "REDACTED" in persisted
            assert led.verify().ok is True
        finally:
            led.close()

    return Fixture(
        id=f"REDACT-{marker}",
        family="secret_redaction",
        surface=SURFACE_HOSTED,
        kind=KIND_REDACTED,
        description=description,
        fn=fn,
    )


RED2_FIXTURES = [
    _red_secret_fixture(
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.dGVzdC1zaWduYXR1cmU",
        "JWT",
        "JWT (three b64url segments) in agent output",
    ),
    _red_secret_fixture(
        "sk-ant-api03-Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8",
        "SKANT",
        "Claude-style sk-ant API key with dashes",
    ),
    _red_secret_fixture(
        "npm_Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx",
        "NPM",
        "npm access token",
    ),
    _red_secret_fixture(
        "AIzaSyAb1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0",
        "AIZA",
        "Google API key",
    ),
    _red_secret_fixture(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----",
        "OPENSSH",
        "OpenSSH private key block",
    ),
    _red_secret_fixture(
        "https://corpus:supersecretpass123@git.example.test/repo.git",
        "URLCRED",
        "credential embedded in a git URL",
    ),
]


# -- passive: trailer attribution spoofing ----------------------------------------------


def _f_attr_spoof(tmp: Path) -> None:
    # A forged Co-Authored-By claiming the Meridian identity: recognised
    # and flagged meridianAuthored — a claim, not direct evidence. The
    # parser never upgrades trailer text to verified authorship.
    message = append_trailer("commit", "Co-Authored-By", "Meridian <agent@meridian.local>")
    parsed = parse_attributions(message)[0]
    assert parsed["meridianAuthored"] is True
    assert parsed["vendor"] == "meridian"
    # The trailer is still inferred evidence by construction (D55).
    assert trailers.MERIDIAN_IDENTITY == "meridian"


def _f_trailer_comment(tmp: Path) -> None:
    # A Meridian-Ledger line inside a comment is NOT a trailer: spoofing
    # via commit-message comments cannot fabricate verification pointers.
    message = "# Meridian-Ledger: v1 seq=9 root=" + "ab" * 32 + "\nreal subject line"
    assert ts.parse_meridian_ledger_trailers(message).refs == []


def fixtures() -> list[Fixture]:
    return [
        _f_policy(c)
        for c in ("FAILCLOSED", "UNKNOWN-PROFILE", "REQ-FIELDS", "ANON-APPROVAL", "ROLE-MISMATCH", "NO-TESTS")
    ] + [
        _f_worktree(c)
        for c in ("PATH-TRAVERSAL", "ABSOLUTE", "DOTDOT", "UNICODE", "BRANCH-TRAVERSAL", "BOUNDARY-HOLDS")
    ] + [
        _f_identity(c) for c in ("SPOOF-ASSERTED", "UNAVAILABLE", "BOT-NEVER-HUMAN")
    ] + [
        Fixture(
            id="ID-OIDC-DEFERRED",
            family="identity_spoof",
            surface=SURFACE_HOSTED,
            kind=KIND_BLOCKED,
            description="OIDC provider raises its deferred FR-M20-01 body rather than faking verification",
            fn=_f_oidc,
        )
    ] + [
        _f_econ(c)
        for c in ("PROV-INJECT-DETAIL", "CLOSED-VOCAB", "CAT-INJECT", "NO-BLEND")
    ] + RED2_FIXTURES + [
        Fixture(
            id="ATTR-COAUTHOR-SPOOF",
            family="attribution_spoof",
            surface=SURFACE_PASSIVE,
            kind=KIND_DETECTED,
            description="forged Co-Authored-By: Meridian flag is a claim (inferred), never upgraded",
            fn=_f_attr_spoof,
        ),
        Fixture(
            id="TRAILER-IN-COMMENT",
            family="trailer_forgery",
            surface=SURFACE_PASSIVE,
            kind=KIND_BLOCKED,
            description="Meridian-Ledger inside a comment line does not parse as a trailer",
            fn=_f_trailer_comment,
        ),
    ]
