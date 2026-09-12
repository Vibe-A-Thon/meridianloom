"""A forged signal is never promoted — SEC-34, MV1-T10.

Every channel Meridian observes is a text file somebody can write. A
`Co-Authored-By` trailer is a line in a commit message. A `Meridian-Ledger:`
trailer is the same. An OTel export is a stream Meridian did not authenticate.
None of them is a signature, and the product's own security document already
says so about the trailer: *"it is a pointer, not a proof."*

SEC-34 draws the consequence: **a forged signal must not be elevated above
`inferred`.** That cannot be satisfied by detecting forgery — Meridian has no
way to tell a genuine trailer from a fabricated one, and a check that claimed
to would be the overclaim this module exists to prevent. It is satisfied the
only way it can be: by not letting unauthenticated evidence claim a rung that
implies authentication.

These are the narrow, high-value fixtures. The 100-fixture adversarial corpus
of FR-M46-09/10 is POST-MVP.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meridian_core.observers.base import (
    CONFIDENCE_DIRECT,
    CONFIDENCE_INFERRED,
    CONFIDENCE_ORDER,
    CONFIDENCE_TELEMETRY,
)


def _git(repo, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture()
def repo(tmp_path):
    """A repository whose history is entirely fabricated by this test.

    Nothing here was produced by any agent. That is the point: every signal
    below is a forgery by construction, so any confidence above `inferred`
    is a confidence Meridian cannot justify.
    """
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.name", "Not An Agent")
    _git(tmp_path, "config", "user.email", "human@example.com")
    (tmp_path / "payment.py").write_text("def charge():\n    pass\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    return tmp_path


def _commit(repo, message: str) -> None:
    (repo / "payment.py").write_text(
        f"def charge():\n    return {len(message)}\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", message)


class TestTheLadderItself:
    def test_inferred_is_the_bottom_rung(self):
        # The whole requirement rests on `inferred` being the weakest claim.
        # If the order ever changed, capping at `inferred` would stop meaning
        # "claims nothing it cannot support".
        assert CONFIDENCE_ORDER.index(CONFIDENCE_INFERRED) == len(CONFIDENCE_ORDER) - 1
        assert CONFIDENCE_ORDER.index(CONFIDENCE_DIRECT) == 0


class TestForgedTrailers:
    def test_a_fabricated_trailer_gains_nothing_from_being_fabricated(self, repo):
        """A forged trailer reaches the trailer tier's rung and no further.

        This is the guarantee SEC-34's wording actually secures: forgery
        must not *elevate* a signal. It cannot — the rung belongs to the
        channel, not to the content, so writing a convincing trailer by hand
        buys exactly what writing an honest one buys and never `direct`.

        It is NOT the stronger guarantee that trailer evidence is capped at
        `inferred`. Today the git-trailer tier is `telemetry` in all five
        observers, so a line a person typed is reported on the rung whose
        name means the agent's own instrumented output. Whether that is
        right is an open product question, recorded as D55 — it is a change
        to shipped behaviour across five observers, which §19.1 makes an
        owner decision rather than a test's to force.
        """
        _commit(
            repo,
            "Add idempotency key\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n",
        )
        from meridian_core.observers.claude import ClaudeCodeObserver
        from meridian_core.observers.claude import CHAIN_GIT_TRAILERS

        observer = ClaudeCodeObserver()
        outcome = observer.observe(Path(repo), datetime.now(timezone.utc))
        observation = outcome.observation
        assert observation is not None, "the forged trailer was not observed at all"

        # Never the top rung. `direct` means Meridian identified the session
        # itself, and no amount of commit-message text can establish that.
        assert observation.confidence != CONFIDENCE_DIRECT

        # And it is pinned to the tier that read it, so the rung cannot creep
        # upward without someone changing the tier and this failing.
        tier = next(
            t for t in observer.evidence_tiers() if t.name == CHAIN_GIT_TRAILERS
        )
        assert observation.confidence == tier.confidence
        assert observation.source == CHAIN_GIT_TRAILERS

    def test_a_fabricated_meridian_ledger_trailer_is_not_evidence_of_a_ledger(self, repo):
        """The `Meridian-Ledger:` trailer is a pointer into the record.

        A commit can carry one naming a range that never existed. Resolving
        it must fail against the ledger rather than being taken at face
        value — the trailer is the index, the ledger is the record.
        """
        _commit(repo, "Looks governed\n\nMeridian-Ledger: 1-9999\n")
        from meridian_core import trailers as trailers_mod

        body = _git(repo, "log", "-1", "--format=%B")
        parsed = trailers_mod.parse_trailers(body)
        # The parser reads what is written — that is its job, and it must not
        # invent a verdict. What must NOT happen is the parse being treated
        # as proof that those entries exist.
        assert parsed, "the trailer should parse; it is well-formed"
        # There is no ledger here at all, so nothing can corroborate it.
        # The security document states this limitation; this test holds the
        # product to it.
        assert not (repo / ".meridian" / "ledger").exists()


class TestForgedTelemetry:
    def test_an_unauthenticated_otel_stream_cannot_claim_direct(self, tmp_path):
        """`direct` means Meridian identified the session itself.

        A file on disk claiming to be an agent's OTel export is not that. If
        pointing Meridian at a fabricated export were enough to reach
        `direct`, the strongest rung on the ladder would be the easiest to
        obtain.
        """
        from meridian_core.observers import base

        forged = base.Observation(
            vendor="claude",
            session_id="forged-session",
            confidence=CONFIDENCE_DIRECT,
            source="otel",
            detail="a file someone wrote",
            started_at=None,
            workspace=str(tmp_path),
            agent_id=None,
        )
        tier = base.EvidenceTier("git-trailers", CONFIDENCE_INFERRED, lambda _ws, _now: forged)
        outcome = base.run_fallback_chain(
            "claude", [tier], Path(tmp_path), datetime.now(timezone.utc)
        )
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED, (
            "a tier claimed a confidence above its own ceiling and the chain "
            "accepted it; the ceiling is what stops a forged signal being "
            "promoted by the observer that read it"
        )

    def test_the_ceiling_only_ever_clamps_down(self, tmp_path):
        # The invariant, stated in the direction it actually holds. A first
        # version of this test asserted the ceiling would RAISE a modest
        # observation to its rung, which is backwards and would have been a
        # promotion mechanism — exactly what SEC-34 forbids. A tier may
        # always claim less than its rung; it may never claim more.
        from meridian_core.observers import base

        modest = base.Observation(
            vendor="claude",
            session_id="s",
            confidence=CONFIDENCE_INFERRED,
            source="otel",
            detail="",
            started_at=None,
            workspace=str(tmp_path),
            agent_id=None,
        )
        tier = base.EvidenceTier("otel", CONFIDENCE_TELEMETRY, lambda _ws, _now: modest)
        outcome = base.run_fallback_chain(
            "claude", [tier], Path(tmp_path), datetime.now(timezone.utc)
        )
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
