"""Vendor evidence-retention windows, volatile capture records and
expiry markers (FR-M44-11/12/13, NFR-37, AC-47; N1 Workstream D tasks
20-22).

FR-M44-11: for every supported vendor, the DOCUMENTED retention window of
each evidence source Meridian depends on, with a citation and the date
the documentation was retrieved. Where a vendor documents no window the
record says ``unknown`` (P26 — never invented). The documented facts
below come from the vendor-documentation review of 6-9 September 2026
(``futures.md``, FUT-022); only windows with a citation carry a day
count.

FR-M44-12 / NFR-37: volatile evidence is captured within its window; each
capture records latency (event -> capture), the achieved margin (the
fraction of the window still remaining at capture time — NFR-37 targets
>= 0.5 under normal operation) and what was unavailable at capture time.
A vendor with an ``unknown`` window cannot report a margin: the record
says so instead of inventing one.

FR-M44-13 / AC-47: when evidence ages past its documented window,
:func:`EvidenceExpiryTracker.markers` emits an explicit
``evidence_expired`` marker NAMING the window that closed. A closed
window is a named coverage gap (wired into metric envelopes as a
:class:`~meridian_core.metrics.coverage.DataGap` with gapClass
``evidence_expired``), never presented as an absence of activity, and the
downgrade is sticky for the session ("within one session", NFR-32).

Zero model calls (FR-M36-07): pure stdlib date arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

#: NFR-37: the volatile-capture margin target — evidence with a documented
#: window is captured with at least 50% of the window remaining.
MARGIN_TARGET = 0.5

#: The marker class a closed window emits (FR-M44-13) — also the DataGap
#: gapClass so metric envelopes name it (FR-M41-12).
EXPIRED_MARKER = "evidence_expired"

#: Date the vendor documentation this map cites was retrieved.
_RETRIEVED = "2026-09-09"


@dataclass(frozen=True)
class RetentionWindow:
    """FR-M44-11: the documented retention of one vendor evidence source.

    ``window_days`` is None when the vendor documents no window — the
    ``documented`` flag is then False, the citation names the reviewed
    documentation, and every derived figure reports ``unknown`` rather
    than a fabricated number (P26).
    """

    vendor: str
    source: str  # the evidence source within the vendor (e.g. session logs)
    window_days: int | None
    citation: str
    retrieved: str = _RETRIEVED
    documented: bool = True
    note: str = ""

    @property
    def window_label(self) -> str:
        """The window's human name — what the expiry marker names."""
        if self.window_days is None:
            return f"{self.vendor} {self.source} (retention window unknown)"
        return f"{self.vendor} {self.source} ({self.window_days} day{'s' if self.window_days != 1 else ''})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "source": self.source,
            "windowDays": self.window_days,
            "citation": self.citation,
            "retrieved": self.retrieved,
            "documented": self.documented,
            **({"note": self.note} if self.note else {}),
        }


#: FR-M44-11: the recorded retention windows of every supported vendor's
#: evidence sources. Copilot's agent-session visibility is the one
#: DOCUMENTED volatile window (24 hours); the other vendors document no
#: retention window for the evidence Meridian depends on, which is
#: recorded as ``unknown`` — never invented.
VENDOR_RETENTION: dict[str, tuple[RetentionWindow, ...]] = {
    "claude": (
        RetentionWindow(
            vendor="claude",
            source="local-session-transcripts",
            window_days=None,
            documented=False,
            citation="Claude Code documentation, accessed 2026-09-09 (futures.md FUT-022)",
            note="local session transcripts are locally erasable; no retention window is documented",
        ),
    ),
    "copilot": (
        RetentionWindow(
            vendor="copilot",
            source="agent-session-logs",
            window_days=1,
            citation="GitHub Docs: monitoring Copilot agentic activity (docs.github.com/en/copilot/how-tos/administer-copilot/manage-for-enterprise/manage-agents/monitor-agentic-activity), accessed 2026-09-09",
            note="agent session visibility is a 24-hour window; capture volatile session evidence inside it (FUT-022)",
        ),
        RetentionWindow(
            vendor="copilot",
            source="audit-events",
            window_days=180,
            citation="GitHub Docs: Copilot audit-log streaming (docs.github.com/en/copilot/concepts/agents/enterprise-management), accessed 2026-09-09",
            note="coarse audit events persist 180 days; they exclude local client prompts",
        ),
    ),
    "cursor": (
        RetentionWindow(
            vendor="cursor",
            source="otel-export",
            window_days=None,
            documented=False,
            citation="Cursor telemetry documentation, accessed 2026-09-09 (futures.md FUT-022)",
            note="OTel export has no historical backfill; no retention window is documented",
        ),
    ),
    "codex": (
        RetentionWindow(
            vendor="codex",
            source="session-evidence",
            window_days=None,
            documented=False,
            citation="Codex documentation, accessed 2026-09-09 (futures.md vendor review)",
            note="no retention window documented for the evidence Meridian depends on",
        ),
    ),
    "devin": (
        RetentionWindow(
            vendor="devin",
            source="audit-log-api",
            window_days=None,
            documented=False,
            citation="Devin (Cognition) documentation, accessed 2026-09-09 (futures.md vendor review)",
            note="enterprise audit-log APIs exist, but no retention window is documented",
        ),
    ),
}


def retention_windows(vendor: str) -> tuple[RetentionWindow, ...]:
    """Every recorded evidence source for ``vendor`` (empty for an
    unsupported vendor — never an error, never fabricated)."""
    return VENDOR_RETENTION.get(vendor, ())


def window_for(vendor: str, source: str) -> RetentionWindow | None:
    """The recorded window for one vendor evidence source; None when the
    vendor/source is not recorded."""
    for window in retention_windows(vendor):
        if window.source == source:
            return window
    return None


def unknown_window(vendor: str, source: str) -> RetentionWindow:
    """The honest ``unknown`` window for an unrecorded vendor/source pair
    (P26) — callers reach for this instead of inventing a number."""
    return RetentionWindow(
        vendor=vendor,
        source=source,
        window_days=None,
        citation="not recorded (FR-M44-11)",
        documented=False,
        note="no documented retention window recorded for this evidence source",
    )


@dataclass(frozen=True)
class CaptureRecord:
    """FR-M44-12 / NFR-37: one volatile-evidence capture, with the
    latency, the achieved margin and what was unavailable."""

    vendor: str
    source: str
    evidence_time: datetime  # when the vendor-side evidence was created
    captured_at: datetime  # when Meridian captured it
    latency_seconds: float  # evidence_time -> captured_at
    window_days: int | None  # the documented window; None = unknown
    window_remaining_days: float | None  # window left at capture time
    achieved_margin: float | None  # fraction of the window remaining
    unavailable: tuple[str, ...] = ()

    @property
    def within_window(self) -> bool:
        """True when captured before the documented window closed."""
        if self.window_days is None:
            return False  # unknown window: nothing provable (P26)
        return self.captured_at <= self.evidence_time + timedelta(
            days=self.window_days
        )

    @property
    def meets_margin_target(self) -> bool:
        """NFR-37: captured with at least MARGIN_TARGET of the window
        remaining. Unknowable windows read False — reported, not assumed."""
        return (
            self.achieved_margin is not None
            and self.achieved_margin >= MARGIN_TARGET
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "source": self.source,
            "evidenceTime": self.evidence_time.isoformat(),
            "capturedAt": self.captured_at.isoformat(),
            "captureLatencySeconds": round(self.latency_seconds, 3),
            "windowDays": self.window_days,
            "windowRemainingDays": (
                round(self.window_remaining_days, 3)
                if self.window_remaining_days is not None
                else None
            ),
            "achievedMargin": self.achieved_margin,
            "unavailable": list(self.unavailable),
            "withinWindow": self.within_window,
            "meetsMarginTarget": self.meets_margin_target,
        }


def record_capture(
    vendor: str,
    source: str,
    evidence_time: datetime,
    *,
    captured_at: datetime | None = None,
    unavailable: tuple[str, ...] | list[str] = (),
) -> CaptureRecord:
    """Record one volatile capture against the vendor's DOCUMENTED window
    (FR-M44-12). Latency and margin are derived here, in the same
    operation as the capture (NFR-34); an unknown window yields
    ``window_days``/``margin`` None — the record says what it cannot
    know, never a plausible number (P25/P26)."""
    captured_at = captured_at or datetime.now(timezone.utc)
    window = window_for(vendor, source) or unknown_window(vendor, source)
    latency = (captured_at - evidence_time).total_seconds()
    window_days = window.window_days
    if window_days is None:
        remaining_days: float | None = None
        margin: float | None = None
    else:
        remaining = timedelta(days=window_days) - (captured_at - evidence_time)
        remaining_days = remaining.total_seconds() / 86400.0
        margin = round(remaining.total_seconds() / (window_days * 86400.0), 6)
    return CaptureRecord(
        vendor=vendor,
        source=source,
        evidence_time=evidence_time,
        captured_at=captured_at,
        latency_seconds=latency,
        window_days=window_days,
        window_remaining_days=remaining_days,
        achieved_margin=margin,
        unavailable=tuple(unavailable),
    )


@dataclass(frozen=True)
class EvidenceExpiry:
    """FR-M44-13 / AC-47: one closed window, explicitly marked — never
    presented as an absence of activity."""

    vendor: str
    source: str
    window_days: int
    window_label: str  # the named window
    evidence_time: datetime
    closed_at: datetime  # evidence_time + window
    marker: str = EXPIRED_MARKER

    @property
    def message(self) -> str:
        return (
            f"evidence_expired: the {self.window_label} window closed at "
            f"{self.closed_at.isoformat()} before capture — this is a named "
            "coverage gap, NOT an absence of activity (FR-M44-13)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "marker": self.marker,
            "vendor": self.vendor,
            "source": self.source,
            "windowDays": self.window_days,
            "windowLabel": self.window_label,
            "evidenceTime": self.evidence_time.isoformat(),
            "closedAt": self.closed_at.isoformat(),
            "message": self.message,
        }

    def to_gap(self, count: int = 1):
        """The envelope DataGap (FR-M41-12): the expired window rides the
        metric's ``gaps`` so the figure names what it lost."""
        from ..metrics.coverage import DataGap

        return DataGap(
            gapClass=EXPIRED_MARKER,
            count=count,
            detail=self.window_label,
        )


def expiry_for(capture: CaptureRecord, now: datetime) -> EvidenceExpiry | None:
    """The expiry marker for one capture at ``now``; None while the
    window is still open (or was never documented). A capture that itself
    landed after the window closed is expired evidence too — the marker
    names the window that was already shut at capture time (FR-M44-13)."""
    if capture.window_days is None:
        return None
    closed_at = capture.evidence_time + timedelta(days=capture.window_days)
    if now < closed_at and capture.within_window:
        return None
    window = window_for(capture.vendor, capture.source)
    label = window.window_label if window is not None else (
        f"{capture.vendor} {capture.source} ({capture.window_days} days)"
    )
    return EvidenceExpiry(
        vendor=capture.vendor,
        source=capture.source,
        window_days=capture.window_days,
        window_label=label,
        evidence_time=capture.evidence_time,
        closed_at=closed_at,
    )


@dataclass
class EvidenceExpiryTracker:
    """Session-lifetime volatile-evidence tracker (FR-M44-12/13, NFR-37).

    Captures recorded here; :meth:`markers` derives the ``evidence_expired``
    markers for every capture whose documented window has closed. Markers
    are STICKY for the process lifetime (one session): once a window is
    marked closed it stays marked — the downgrade happens within one
    session and never reopens silently (NFR-32/AC-47).
    """

    _captures: list[CaptureRecord] = field(default_factory=list)
    _expired: dict[tuple[str, str], EvidenceExpiry] = field(default_factory=dict)

    def record(self, capture: CaptureRecord) -> None:
        self._captures.append(capture)

    def markers(self, now: datetime | None = None) -> list[EvidenceExpiry]:
        """Every closed window, named — sticky within the session."""
        now = now or datetime.now(timezone.utc)
        for capture in self._captures:
            key = (capture.vendor, capture.source)
            if key in self._expired:
                continue
            marker = expiry_for(capture, now)
            if marker is not None:
                self._expired[key] = marker
        return sorted(
            self._expired.values(),
            key=lambda marker: (marker.vendor, marker.source),
        )

    def gaps(self, now: datetime | None = None):
        """The FR-M41-12 DataGaps for the metric envelope — one named gap
        per closed window, so a figure that lost volatile evidence says so
        in the same operation (AC-47)."""
        return [marker.to_gap() for marker in self.markers(now)]

    def warnings(self, now: datetime | None = None) -> list[str]:
        """The marker messages for observer health/sessions surfaces."""
        return [marker.message for marker in self.markers(now)]

    @property
    def downgraded(self) -> bool:
        """AC-47: True once any window closed this session — the affected
        coverage claim is downgraded within one session."""
        return bool(self._expired)
