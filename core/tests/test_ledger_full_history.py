"""Governance and privacy must see the whole ledger, not its first page.

``Ledger.query`` returns at most 1,000 rows, oldest first, however large a
``limit`` is asked for. Callers that read once and treated the result as
complete were blind to everything after row 1,000 (audit CLD-B01):

* a merge **halt** recorded after 1,000 gate entries was invisible — the merge
  was not blocked (fails open);
* an identity **revoked** after 1,000 revocations could still approve;
* **erasures** after the 1,000th were not replayed into a restored backup, so
  an erased subject became readable again;
* a signed evidence **bundle** claimed a range but held only its first
  1,000 entries.

Each test below constructs the 1,001st-row case, so each fails on the old
code. ``TestNoUnpaginatedReads`` keeps the class of bug from returning.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from meridian_core.governance import merge_gate, policy, revocations
from meridian_core.ledger import privacy
from meridian_core.ledger.bundle import build_bundle
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from test_merge_gate import APPROVER, PACK_TEXT, append_approval, append_halt

PAGE = Ledger.QUERY_PAGE
PACKAGE = Path(__file__).resolve().parents[1] / "meridian_core"


def _gate_noise(ledger: Ledger, index: int) -> None:
    ledger.append(
        {
            "story_id": "gate:noise", "phase": "review", "loop_id": "governance",
            "loop_iteration": 1, "actor_id": "governor", "actor_version": "0",
            "actor_kind": "meta", "policy_version": "governance/v2",
            "action_type": "gate", "decision": "passed", "vendor": "meridian",
            "observation_confidence": "direct",
            "input": json.dumps({"method": "gate.evaluate", "i": index}),
        }
    )


@pytest.fixture(scope="module")
def pack() -> policy.PolicyPack:
    parsed = policy.parse_policy_pack(PACK_TEXT, "test-pack")
    assert parsed.errors == []
    return parsed


def _fresh(tmp_path_factory, name: str) -> Ledger:
    return Ledger(tmp_path_factory.mktemp(name) / "ledger", EphemeralSigningKeyProvider())


@pytest.fixture(scope="module")
def late_halt_ledger(tmp_path_factory):
    """One approval, then more than a page of other gate rows, then a halt."""
    ledger = _fresh(tmp_path_factory, "late-halt")
    append_approval(ledger, "main", "a" * 40)
    for i in range(PAGE):
        _gate_noise(ledger, i)
    append_halt(ledger, "incident: leaked credential", subject="main")
    yield ledger
    ledger.close()


@pytest.fixture(scope="module")
def late_approval_ledger(tmp_path_factory):
    """More than a page of approvals for other subjects, then the one that matters."""
    ledger = _fresh(tmp_path_factory, "late-approval")
    for i in range(PAGE):
        append_approval(ledger, f"other-{i}", "b" * 40)
    append_approval(ledger, "main", "a" * 40)
    yield ledger
    ledger.close()


@pytest.fixture(scope="module")
def late_revocation_ledger(tmp_path_factory):
    ledger = _fresh(tmp_path_factory, "late-revoke")
    for i in range(PAGE):
        revocations.record_revocation(ledger, email=f"user{i}@example.com", reason="noise")
    revocations.record_revocation(ledger, email="mallory@example.com", reason="compromised")
    yield ledger
    ledger.close()


@pytest.fixture(scope="module")
def late_erasure_ledger(tmp_path_factory):
    ledger = _fresh(tmp_path_factory, "late-erase")
    controller = privacy.PrivacyController(ledger)
    for i in range(PAGE + 1):
        controller.erase_subject(f"subject-{i}", reason="request")
    yield ledger, controller
    ledger.close()


# -- the primitive -----------------------------------------------------------


class TestIterQuery:
    def test_walks_past_the_page_size_in_order(self, late_halt_ledger):
        rows = list(late_halt_ledger.iter_query())
        assert len(rows) == PAGE + 2
        assert [r["seq"] for r in rows] == sorted(r["seq"] for r in rows)
        assert [r["seq"] for r in rows] == list(range(1, PAGE + 3))

    def test_a_single_query_really_is_truncated(self, late_halt_ledger):
        # The premise of the whole bug: even a huge limit returns one page.
        assert len(late_halt_ledger.query(limit=100_000)) == PAGE
        assert len(late_halt_ledger.query_all()) == PAGE + 2

    def test_filters_apply_across_pages(self, late_halt_ledger):
        assert len(late_halt_ledger.query_all(action_type="gate")) == PAGE + 1
        assert len(late_halt_ledger.query_all(action_type="approval")) == 1

    def test_max_rows_is_a_total_not_a_page(self, late_halt_ledger):
        # More than one page, fewer than the ledger holds (1,002 rows).
        assert len(late_halt_ledger.query_all(max_rows=PAGE + 1)) == PAGE + 1
        assert len(late_halt_ledger.query_all(max_rows=3)) == 3

    def test_after_sequence_resumes(self, late_halt_ledger):
        rows = late_halt_ledger.query_all(after_sequence=PAGE)
        assert [r["seq"] for r in rows] == [PAGE + 1, PAGE + 2]

    def test_empty_result_is_empty(self, late_halt_ledger):
        assert late_halt_ledger.query_all(action_type="nothing-like-this") == []


# -- the fail-open defects ---------------------------------------------------


class TestHaltAfterAPage:
    def test_a_late_halt_is_visible(self, late_halt_ledger):
        assert merge_gate.active_halts(late_halt_ledger, "main")

    def test_a_late_halt_blocks_the_merge(self, late_halt_ledger, pack):
        verdict = merge_gate.check_merge(late_halt_ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.halted is True
        assert verdict.allowed is False, "an approved change merged despite a halt in force"

    def test_a_halt_for_another_subject_does_not_block(self, late_halt_ledger, pack):
        # Control: the halt is scoped to "main"; another branch stays allowed
        # to reach the approval step (and is refused only for lacking one).
        verdict = merge_gate.check_merge(late_halt_ledger, pack, subject="develop", head_commit="a" * 40)
        assert verdict.halted is False


class TestApprovalAfterAPage:
    def test_a_late_approval_counts(self, late_approval_ledger, pack):
        verdict = merge_gate.check_merge(late_approval_ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is True
        assert verdict.approval is not None and verdict.approval.approver == APPROVER


class TestRevocationAfterAPage:
    def test_a_late_revocation_is_in_force(self, late_revocation_ledger):
        assert revocations.revoked_at(late_revocation_ledger, "mallory@example.com")

    def test_early_revocations_still_count(self, late_revocation_ledger):
        assert revocations.revoked_at(late_revocation_ledger, "user0@example.com")

    def test_an_unrevoked_identity_is_not_revoked(self, late_revocation_ledger):
        assert not revocations.revoked_at(late_revocation_ledger, "alice@example.com")

    def test_the_full_set_is_returned(self, late_revocation_ledger):
        assert len(revocations.active_revocations(late_revocation_ledger)) == PAGE + 1


class TestErasureAfterAPage:
    def test_every_erasure_is_listed(self, late_erasure_ledger):
        _ledger, controller = late_erasure_ledger
        events = controller.erasures()
        assert len(events) == PAGE + 1
        assert events[-1].subject_id == f"subject-{PAGE}"

    def test_a_restored_backup_has_every_subject_shredded_again(self, late_erasure_ledger):
        _ledger, controller = late_erasure_ledger

        class Restored:
            def __init__(self) -> None:
                self.shredded: list[str] = []

            def shred_subject(self, subject_id: str) -> bool:
                self.shredded.append(subject_id)
                return True

        restored = Restored()
        assert controller.replay_erasures_into(restored) == PAGE + 1
        assert f"subject-{PAGE}" in restored.shredded, (
            "the newest erasure was not replayed: that subject would be readable again after a restore"
        )


class TestBundleCompleteness:
    def test_a_bundle_holds_every_entry_in_its_stated_range(self, late_halt_ledger):
        bundle = build_bundle(late_halt_ledger, {})
        stated = bundle["range"]["toSequence"] - bundle["range"]["fromSequence"] + 1
        assert stated == PAGE + 2
        assert len(bundle["entries"]) == stated, (
            f"bundle claims {stated} entries but carries {len(bundle['entries'])}"
        )


# -- keep it that way --------------------------------------------------------

#: `.query(` calls that are legitimately single-page: an RPC pass-through that
#: hands the page and cursor to the client, or a bounded sequence range.
ALLOWED_QUERY_CONTEXT = "after_sequence"


def _query_calls(root: Path):
    for path in sorted(root.rglob("*.py")):
        if path.parent.name == "ledger" and path.name == "core.py":
            continue  # the definition, and iter_query's own page loop
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "query"
            ):
                yield path, node


class TestNoUnpaginatedReads:
    def test_no_module_reads_one_page_and_treats_it_as_complete(self):
        offenders = []
        for path, node in _query_calls(PACKAGE):
            names = {keyword.arg for keyword in node.keywords}
            paged = "after_sequence" in names or {"from_sequence", "to_sequence"} <= names
            if not paged:
                offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
        assert offenders == [], (
            "single-page ledger.query() reads (use iter_query/query_all for full history, or "
            "walk after_sequence): " + ", ".join(offenders)
        )

    def test_no_query_asks_for_more_than_a_page(self):
        # A limit above 1,000 is silently clamped, so it only ever misleads.
        offenders = []
        for path, node in _query_calls(PACKAGE):
            for keyword in node.keywords:
                if keyword.arg == "limit" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, int) and keyword.value.value > PAGE:
                        offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
        assert offenders == []

    def test_the_guard_can_fail(self, tmp_path):
        # Negative control: the same walk over a file with the old pattern.
        probe = tmp_path / "probe.py"
        probe.write_text("def f(ledger):\n    return ledger.query(action_type='gate', limit=1000)\n")
        found = list(_query_calls(tmp_path))
        assert len(found) == 1
        names = {keyword.arg for keyword in found[0][1].keywords}
        assert not ("after_sequence" in names or {"from_sequence", "to_sequence"} <= names)
