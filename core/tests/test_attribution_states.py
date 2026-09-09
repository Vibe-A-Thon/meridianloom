"""Three-state attribution and the closed unknown-reason vocabulary
(FR-M41-04, FR-M41-05; principles P26/J3; N1 Workstream B T07/T08).

The binding rule under test: every span carries exactly one of
``agent`` / ``human`` / ``unattributed``, decided by positive evidence
only. ``human = not agent`` is BANNED — derivation by subtraction — so
these tests assert the human state requires positive human evidence and
that no code path computes a state as a complement.
"""

from __future__ import annotations

from meridian_core.attribution import heuristics, spans
from meridian_core.attribution.states import (
    ATTRIBUTION_AGENT,
    ATTRIBUTION_CONTRACT_VERSION,
    ATTRIBUTION_HUMAN,
    ATTRIBUTION_STATES,
    ATTRIBUTION_UNATTRIBUTED,
    PROVENANCE_STATES,
    UNKNOWN_REASONS,
    UNKNOWN_REASON_VOCABULARY_VERSION,
    decide_attribution,
    is_unknown_reason,
)
from test_attribution import T0, git

INSTALL_T = 1_735_689_600  # 2025-01-01T00:00:00Z — the installation fact


class TestDecideAttribution:
    def test_states_are_exactly_three_and_closed(self):
        assert ATTRIBUTION_STATES == ("agent", "human", "unattributed")

    def test_agent_requires_positive_agent_evidence(self):
        state, weight = decide_attribution(agent_points=2, human_points=0)
        assert state == ATTRIBUTION_AGENT
        assert weight == 1.0

    def test_human_requires_positive_human_evidence(self):
        # The banned derivation would label this human because it is "not
        # agent" — positive-evidence-only says unattributed instead.
        state, weight = decide_attribution(agent_points=0, human_points=0)
        assert state == ATTRIBUTION_UNATTRIBUTED
        assert weight == 0.5

    def test_never_derives_human_by_subtraction(self):
        # Agent evidence present but non-dominant (weight 0.5): neither
        # state may be claimed, and human may NOT appear as the complement
        # of agent.
        state, _ = decide_attribution(agent_points=1, human_points=1)
        assert state == ATTRIBUTION_UNATTRIBUTED

    def test_dominant_human_evidence_is_human(self):
        state, weight = decide_attribution(agent_points=0, human_points=2)
        assert state == ATTRIBUTION_HUMAN
        assert weight == 0.0

    def test_middle_band_is_unattributed_not_mixed(self):
        # 1:1 evidence — non-dominant either way.
        state, weight = decide_attribution(agent_points=1, human_points=1)
        assert state == ATTRIBUTION_UNATTRIBUTED
        assert weight == 0.5


class TestUnknownReasonVocabulary:
    def test_vocabulary_is_the_six_closed_reasons(self):
        assert UNKNOWN_REASONS == (
            "no_signal",
            "formatter_rewrite",
            "squashed_history",
            "pre_installation",
            "unsupported_vendor",
            "excluded_path",
        )

    def test_vocabulary_is_versioned(self):
        assert UNKNOWN_REASON_VOCABULARY_VERSION >= 1

    def test_reason_admission_is_closed(self):
        for reason in UNKNOWN_REASONS:
            assert is_unknown_reason(reason)
        assert not is_unknown_reason("some_new_reason")
        assert not is_unknown_reason("")
        assert not is_unknown_reason(None)

    def test_provenance_states_are_the_four(self):
        assert PROVENANCE_STATES == (
            "observed",
            "inferred",
            "unknown",
            "redacted",
        )

    def test_contract_version_recorded(self):
        assert ATTRIBUTION_CONTRACT_VERSION.startswith("attrib-provenance/v")


class TestClassifyThreeState:
    def test_agent_like_change_is_agent(self, repo):
        (repo / "agent.py").write_text(
            "".join(f"line {i}\n" for i in range(60)), encoding="utf-8"
        )
        result = heuristics.classify(repo, paths=["agent.py"])
        (file,) = result.files
        assert file.attribution == ATTRIBUTION_AGENT
        assert file.unknown_reason is None

    def test_human_like_change_is_human(self, repo):
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nfour\n", encoding="utf-8"
        )
        result = heuristics.classify(repo, paths=["src/app.txt"])
        (file,) = result.files
        assert file.attribution == ATTRIBUTION_HUMAN
        assert file.unknown_reason is None

    def test_no_signal_is_unattributed_with_reason(self, repo):
        # 8 added lines as hunks 6+1+1: burst 8 (< 10), multi-line rate
        # 1/3 = 0.33 (between the cutoffs) — no evidence point fires, so
        # the honest answer is unattributed with the reason recorded.
        base = [f"L{i}" for i in range(80)]
        (repo / "src" / "app.txt").write_text("\n".join(base) + "\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "long base", date=T0)
        out: list[str] = []
        edits = {10: [f"H{i}" for i in range(6)], 40: ["X40"], 60: ["X60"]}
        for index, text in enumerate(base):
            out.append(text)
            if index in edits:
                out.extend(edits[index])
        (repo / "src" / "app.txt").write_text(
            "\n".join(out) + "\n", encoding="utf-8"
        )
        result = heuristics.classify(repo, paths=["src/app.txt"])
        (file,) = result.files
        assert file.attribution == ATTRIBUTION_UNATTRIBUTED
        assert file.unknown_reason == "no_signal"
        assert file.agent_weight == 0.5
        assert file.unknown_reason_version == UNKNOWN_REASON_VOCABULARY_VERSION

    def test_excluded_path_is_reported_not_dropped(self, repo):
        (repo / "dist").mkdir(exist_ok=True)
        (repo / "dist" / "bundle.js").write_text(
            "".join(f"line {i}\n" for i in range(80)), encoding="utf-8"
        )
        (repo / "agent.py").write_text(
            "".join(f"line {i}\n" for i in range(60)), encoding="utf-8"
        )
        files = heuristics.classify(repo, excluded_paths=["dist/"]).files
        by_path = {file.path: file for file in files}
        excluded = by_path["dist/bundle.js"]
        assert excluded.attribution == ATTRIBUTION_UNATTRIBUTED
        assert excluded.unknown_reason == "excluded_path"
        # The non-excluded file classifies normally.
        assert by_path["agent.py"].attribution == ATTRIBUTION_AGENT

    def test_glob_exclusion_matches_basenames(self, repo):
        (repo / "pkg.lock").write_text(
            "".join(f"line {i}\n" for i in range(60)), encoding="utf-8"
        )
        result = heuristics.classify(repo, excluded_paths=["*.lock"])
        (file,) = result.files
        assert file.unknown_reason == "excluded_path"


class TestSpanClassifier:
    def test_trailer_is_agent_observed(self):
        span = spans.classify_span(
            author_name="Dev D",
            author_email="dev@example.com",
            message="add feature\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n",
            author_time="2025-06-01T12:00:00+00:00",
            installed_at=INSTALL_T,
        )
        assert span.state == ATTRIBUTION_AGENT
        assert span.confidence == "observed"
        assert span.unknown_reason is None

    def test_supported_bot_marker_is_agent(self):
        span = spans.classify_span(
            author_name="copilot[bot]",
            author_email="copilot@github.com",
            message="suggest",
            installed_at=INSTALL_T,
        )
        assert span.state == ATTRIBUTION_AGENT
        assert span.confidence == "observed"

    def test_unsupported_bot_marker_reason_recorded(self):
        span = spans.classify_span(
            author_name="builderbot[bot]",
            author_email="builderbot@bots.example.com",
            message="auto build",
            installed_at=INSTALL_T,
        )
        assert span.state == ATTRIBUTION_UNATTRIBUTED
        assert span.unknown_reason == "unsupported_vendor"
        assert span.reason_version == UNKNOWN_REASON_VOCABULARY_VERSION

    def test_formatter_sweep_reason(self):
        span = spans.classify_span(
            author_name="Dev D",
            author_email="dev@example.com",
            message="chore: run black",
            installed_at=INSTALL_T,
        )
        assert span.state == ATTRIBUTION_UNATTRIBUTED
        assert span.unknown_reason == "formatter_rewrite"

    def test_squash_merge_reason(self):
        span = spans.classify_span(
            author_name="Lead L",
            author_email="lead@example.com",
            message="Feature branch work (#142)",
            installed_at=INSTALL_T,
        )
        assert span.state == ATTRIBUTION_UNATTRIBUTED
        assert span.unknown_reason == "squashed_history"

    def test_pre_installation_reason(self):
        span = spans.classify_span(
            author_name="Old Dev",
            author_email="old@example.com",
            message="legacy change",
            author_time="2023-05-04T10:00:00+00:00",
            installed_at=INSTALL_T,
        )
        assert span.state == ATTRIBUTION_UNATTRIBUTED
        assert span.unknown_reason == "pre_installation"
        assert span.confidence == "inferred"

    def test_pre_installation_trailer_never_observed(self):
        # FR-M41-16: trailer evidence on a pre-installation commit is
        # inferred — Meridian was not there to observe the session.
        span = spans.classify_span(
            author_name="Dev D",
            author_email="dev@example.com",
            message="old work\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n",
            author_time="2023-05-04T10:00:00+00:00",
            installed_at=INSTALL_T,
        )
        assert span.state == ATTRIBUTION_AGENT
        assert span.confidence == "inferred"

    def test_plain_human_author_is_human_observed(self):
        span = spans.classify_span(
            author_name="Dev D",
            author_email="dev@example.com",
            message="hand-written change",
            author_time="2025-06-01T12:00:00+00:00",
            installed_at=INSTALL_T,
        )
        assert span.state == ATTRIBUTION_HUMAN
        assert span.confidence == "observed"

    def test_excluded_span_reports_excluded_path(self):
        span = spans.classify_span(
            author_name="Dev D",
            author_email="dev@example.com",
            message="anything",
            excluded=True,
        )
        assert span.state == ATTRIBUTION_UNATTRIBUTED
        assert span.unknown_reason == "excluded_path"
        assert span.confidence == "unknown"

    def test_every_answer_records_contract_version(self):
        span = spans.classify_span(
            author_name="Dev D", author_email="dev@example.com"
        )
        assert span.contract_version == ATTRIBUTION_CONTRACT_VERSION
