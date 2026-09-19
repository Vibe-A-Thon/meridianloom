"""Three-state span attribution over committed git evidence (FR-M41-04,
FR-M41-05; N1 Workstream B T07/T08; FUT-026 FR-M41-16's confidence rule).

A *span* is a run of lines introduced by one commit (what ``git blame``
returns per line). :func:`classify_span` maps the span's introducing
commit facts — author identity, message, timestamp — to one of the three
states, by positive evidence only, in a fixed precedence order:

1. ``excluded_path`` — the path is excluded from attribution: reported,
   never silently dropped.
2. ``agent`` — a ``Co-Authored-By`` trailer resolving to a known vendor
   (git-trailer evidence sits at the observed rung per D34), or a
   supported author bot marker.
3. ``formatter_rewrite`` — the introducing commit is a mechanical
   formatting sweep; its lines carry no authorship signal.
4. ``squashed_history`` — the commit is a squash merge whose per-author
   detail was destroyed.
5. ``unsupported_vendor`` — author markers indicate a bot from a vendor
   Meridian does not recognise: no positive state can be claimed.
6. ``human`` — a human author identity with no contradicting marker.
7. ``pre_installation`` / ``no_signal`` — nothing fired: the reason
   names why (the commit predates Meridian's installation and no signal
   survives, or there is simply no signal).

FR-M41-16 (FUT-026): attribution over commits predating Meridian's
installation is ``inferred`` — never ``observed`` — even when the git
evidence (trailer, marker) is directly read: Meridian was not there to
observe the session. ``installed_at`` (epoch seconds) is the installation
fact; without it no downgrade applies.

Every answer records the vocabulary version and the contract version it
was produced under (FR-M41-01/05), so evaluated corpora stay comparable
across vocabulary changes.

Zero model calls (FR-M36-07): regex and dictionary lookups only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..trailers import VENDOR_EMAILS, parse_attributions
from .states import (
    ATTRIBUTION_AGENT,
    ATTRIBUTION_CONTRACT_VERSION,
    ATTRIBUTION_HUMAN,
    ATTRIBUTION_UNATTRIBUTED,
    UNKNOWN_REASONS,
    UNKNOWN_REASON_EXCLUDED_PATH,
    UNKNOWN_REASON_FORMATTER_REWRITE,
    UNKNOWN_REASON_NO_SIGNAL,
    UNKNOWN_REASON_PRE_INSTALLATION,
    UNKNOWN_REASON_SQUASHED_HISTORY,
    UNKNOWN_REASON_UNSUPPORTED_VENDOR,
    UNKNOWN_REASON_VOCABULARY_VERSION,
)

__all__ = ["SpanAttribution", "classify_span"]

#: Formatter-sweep subjects: the introducing commit rewrites style, not
#: authorship. Matched against the subject line only.
_FORMATTER_RE = re.compile(
    r"^\s*(chore(\([^)]*\))?:\s*)?(run\s+)?"
    r"(black|prettier|eslint|isort|autopep8|clang-format|gofmt|rustfmt|yapf)"
    r"\b|^\s*(re?format|lint|whitespace[- ]?only|style:\s*format)\b",
    re.IGNORECASE,
)

#: Squash shapes: git's own squash output, or a PR-style squash-merge
#: subject ("Title (#123)") whose per-author trailers were destroyed.
_SQUASH_RE = re.compile(r"squashed commit of the following", re.IGNORECASE)
_SQUASH_MERGE_RE = re.compile(r"\(#[0-9]+\)\s*$")

#: Supported agent vendor names, for author-marker resolution (trailers
#: resolve through VENDOR_EMAILS the same way).
_SUPPORTED_VENDORS = frozenset(VENDOR_EMAILS.values()) | {"meridian"}

_BOT_NAME_RE = re.compile(r"\[bot\]\s*$", re.IGNORECASE)
_BOT_EMAIL_RE = re.compile(r"(^|[-._])(bot)([-._@]|$)|\[bot\]@|noreply@", re.IGNORECASE)


@dataclass(frozen=True)
class SpanAttribution:
    """The three-state answer for one span, with its evidence labelled."""

    state: str  # agent | human | unattributed (FR-M41-04)
    unknown_reason: str | None  # closed vocabulary when unattributed (FR-M41-05)
    reason_version: int  # UNKNOWN_REASON_VOCABULARY_VERSION recorded with the answer
    confidence: str  # observed | inferred | unknown (FR-M41-02 states)
    evidence: str  # which positive evidence decided the state, for audit
    contract_version: str = ATTRIBUTION_CONTRACT_VERSION


def _to_epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _pre_installation(author_epoch: float | None, installed_at: Any) -> bool:
    installed_epoch = _to_epoch(installed_at)
    if installed_epoch is None or author_epoch is None:
        return False
    return author_epoch < installed_epoch


def _supported_vendor_from_marker(name: str, email: str) -> str | None:
    """A supported vendor named by the author's bot marker, if any."""
    haystack = f"{name} {email}".lower()
    for marker in _SUPPORTED_VENDORS:
        if marker in haystack:
            return marker
    email_key = email.strip().lower()
    return VENDOR_EMAILS.get(email_key)


def classify_span(
    *,
    author_name: str,
    author_email: str,
    message: str = "",
    author_time: Any = None,
    installed_at: Any = None,
    excluded: bool = False,
) -> SpanAttribution:
    """Classify one span's introducing commit into the three states.

    Positive evidence only — the states are mutually exclusive and no
    state is derived by subtracting the others (FR-M41-04).
    ``installed_at`` (epoch seconds or ISO 8601) is Meridian's
    installation fact; spans from earlier commits are labelled
    ``inferred``, never ``observed`` (FR-M41-16).
    """
    author_epoch = _to_epoch(author_time)
    backfilled = _pre_installation(author_epoch, installed_at)

    if excluded:
        return SpanAttribution(
            ATTRIBUTION_UNATTRIBUTED,
            UNKNOWN_REASON_EXCLUDED_PATH,
            UNKNOWN_REASON_VOCABULARY_VERSION,
            "unknown",
            "path excluded from attribution — no signal sought",
        )

    # 1. Agent trailer (observed rung per D34) — positive agent evidence.
    trailers = parse_attributions(message or "")
    recognised = [
        record
        for record in trailers
        if record.get("vendor") not in (None, "unknown")
    ]
    if recognised:
        vendor = recognised[0]["vendor"]
        confidence = "inferred" if backfilled else "observed"
        return SpanAttribution(
            ATTRIBUTION_AGENT,
            None,
            UNKNOWN_REASON_VOCABULARY_VERSION,
            confidence,
            f"Co-Authored-By trailer resolves to vendor '{vendor}'"
            + (" (pre-installation commit — inferred per FR-M41-16)" if backfilled else ""),
        )

    subject = (message or "").splitlines()[0] if (message or "").splitlines() else ""

    # 2. Formatter sweep: the lines carry no authorship signal.
    if subject and _FORMATTER_RE.search(subject):
        return SpanAttribution(
            ATTRIBUTION_UNATTRIBUTED,
            UNKNOWN_REASON_FORMATTER_REWRITE,
            UNKNOWN_REASON_VOCABULARY_VERSION,
            "inferred",
            f"formatter sweep commit ('{subject.strip()}')",
        )

    # 3. Squash merge: per-author detail destroyed.
    if _SQUASH_RE.search(message or "") or _SQUASH_MERGE_RE.search(subject):
        return SpanAttribution(
            ATTRIBUTION_UNATTRIBUTED,
            UNKNOWN_REASON_SQUASHED_HISTORY,
            UNKNOWN_REASON_VOCABULARY_VERSION,
            "inferred",
            f"squash merge subject ('{subject.strip()}')",
        )

    # 4. Author bot markers: supported vendor -> agent; unknown bot ->
    # unattributed with the reason recorded.
    is_bot = bool(_BOT_NAME_RE.search(author_name or "")) or bool(
        _BOT_EMAIL_RE.search(author_email or "")
    )
    if is_bot:
        vendor = _supported_vendor_from_marker(author_name or "", author_email or "")
        if vendor is not None:
            confidence = "inferred" if backfilled else "observed"
            return SpanAttribution(
                ATTRIBUTION_AGENT,
                None,
                UNKNOWN_REASON_VOCABULARY_VERSION,
                confidence,
                f"author marker resolves to supported vendor '{vendor}'"
                + (" (pre-installation commit — inferred per FR-M41-16)" if backfilled else ""),
            )
        return SpanAttribution(
            ATTRIBUTION_UNATTRIBUTED,
            UNKNOWN_REASON_UNSUPPORTED_VENDOR,
            UNKNOWN_REASON_VOCABULARY_VERSION,
            "inferred",
            f"bot author '{author_name} <{author_email}>' matches no supported vendor",
        )

    # 5. Human author identity: positive human evidence. FR-M41-16
    # (FUT-026): repository history predating Meridian's installation IS
    # attributed from git history alone — at inferred confidence, never
    # observed.
    if author_name.strip() and author_name.strip().lower() != "unknown":
        confidence = "inferred" if backfilled else "observed"
        return SpanAttribution(
            ATTRIBUTION_HUMAN,
            None,
            UNKNOWN_REASON_VOCABULARY_VERSION,
            confidence,
            f"human author '{author_name} <{author_email}>' with no agent markers"
            + (" (pre-installation commit — inferred per FR-M41-16)" if backfilled else ""),
        )

    # 6. Nothing fired. The reason names WHY: pre-installation explains
    # why no authorship signal survives; otherwise there is simply no
    # signal (reported, never absorbed — P26).
    if backfilled:
        return SpanAttribution(
            ATTRIBUTION_UNATTRIBUTED,
            UNKNOWN_REASON_PRE_INSTALLATION,
            UNKNOWN_REASON_VOCABULARY_VERSION,
            "inferred",
            "commit predates Meridian installation and no authorship signal survives in git",
        )
    return SpanAttribution(
        ATTRIBUTION_UNATTRIBUTED,
        UNKNOWN_REASON_NO_SIGNAL,
        UNKNOWN_REASON_VOCABULARY_VERSION,
        "unknown",
        "no authorship signal in the introducing commit",
    )


def reason_vocabulary() -> tuple[str, ...]:
    """The closed vocabulary, exposed for corpus/evaluation assertions."""
    return UNKNOWN_REASONS
