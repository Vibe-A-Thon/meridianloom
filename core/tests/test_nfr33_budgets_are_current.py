"""NFR-33: the recorded budget figures must describe the code that exists.

This file exists because of a specific failure, not a hypothetical one.

`BUILD_STATE.md` recorded **NFR-33 PASS** with figures measured at commit
`45928f1`. Two commits later `e027749` added the attribution-coverage floor
and `8574658` made each greenfield/brownfield bucket a real computation. Both
made the metrics meaningfully slower. Nobody re-measured, so a criterion
recorded as passing was failing for two commits, in the file that calls
itself the resumption state of record.

The measurement is not the fragile part — `test_full_history_metrics.py`
measures honestly every time it runs. The fragile part is the *claim written
down beside it*, which outlives the measurement and cannot be falsified by
reading it.

So this test reads the claim and checks two things a human reading
BUILD_STATE cannot check by eye:

  1. every metric under a budget is actually named in the recorded figures —
     a metric that gains a budget and is never recorded is invisible;
  2. the record does not still cite a commit as its evidence without saying
     the figures were re-measured after the features that changed them.

It deliberately does not assert specific timings. Timings belong in the
benchmark, which runs in CI on every push. What belongs here is the link
between the benchmark and the sentence somebody will read in six months and
believe.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUILD_STATE = REPO / "BUILD_STATE.md"
BENCHMARK = REPO / "core" / "tests" / "test_full_history_metrics.py"

# The metrics the benchmark puts under the NFR-33 budget. Read from the
# benchmark itself rather than duplicated, so adding a budgeted metric
# there fails here until it is also recorded.
BUDGET_LABEL = re.compile(r'_timed\(\s*"([^"]+)"')


def budgeted_metrics() -> set[str]:
    return set(BUDGET_LABEL.findall(BENCHMARK.read_text(encoding="utf-8")))


@pytest.mark.skipif(
    not BUILD_STATE.exists(), reason="BUILD_STATE.md is not in this checkout"
)
class TestRecordedBudgetsAreCurrent:
    def test_the_benchmark_actually_budgets_something(self):
        # A guard on the guard: if the regex stops matching because the
        # benchmark was restructured, every assertion below would pass
        # vacuously and this file would become decoration.
        metrics = budgeted_metrics()
        assert len(metrics) >= 5, (
            "NFR-33 benchmark labels could not be read from "
            f"{BENCHMARK.name}; this check cannot verify the record"
        )

    def test_every_budgeted_metric_appears_in_the_recorded_figures(self):
        text = BUILD_STATE.read_text(encoding="utf-8")
        assert "NFR-33" in text, "BUILD_STATE.md records no NFR-33 figures at all"

        # The recorded figures live in the sentence that names NFR-33.
        recorded = " ".join(
            line for line in text.splitlines() if "NFR-33" in line
        )
        # The record uses the short name (rejectionRate); the benchmark uses
        # the RPC name and sometimes qualifies it ("spend/forecast (least
        # squares)"). Compare on the bare metric token.
        missing = sorted(
            {
                short
                for short in (
                    metric.split("/")[-1].split("(")[0].strip()
                    for metric in budgeted_metrics()
                )
                if short not in recorded
            }
        )
        assert not missing, (
            "these metrics are under an NFR-33 budget but are not named in "
            f"BUILD_STATE's recorded figures: {', '.join(missing)}. A budget "
            "nobody records is a budget nobody notices breaking."
        )

    def test_the_record_does_not_rest_on_a_bare_commit_citation(self):
        recorded = " ".join(
            line
            for line in BUILD_STATE.read_text(encoding="utf-8").splitlines()
            if "NFR-33" in line
        )
        # A figure attributed only to a commit hash is the exact shape the
        # stale claim had: true once, unfalsifiable later. The record must
        # say when it was measured, so a reader can ask whether anything has
        # landed since.
        cites_commit = re.search(r"\(([0-9a-f]{7,40})\)", recorded)
        states_when = re.search(
            r"re-measured|measured\s+\d|\d{1,2}\s+\w+ember|\d{1,2}\s+\w+",
            recorded,
        )
        assert states_when or not cites_commit, (
            "BUILD_STATE attributes the NFR-33 figures to a commit without "
            "saying when they were measured. That is how the last stale "
            "PASS happened: the citation stayed true while the code moved."
        )
