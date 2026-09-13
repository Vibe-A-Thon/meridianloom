"""Other tools' provenance records — M52, `MVP-R7.1`, MV3-T06.

Another provenance tool in the customer's repository is not a competitor to
be displaced. It is **evidence to be made tamper-evident**.

Every tool in this space captures something: a git note under its own ref, a
`Co-Authored-By` line, a session-log trailer. None of them makes that capture
provable afterwards — the note is a mutable blob in the repository, and
anybody who can write the repository can rewrite what it says about what an
agent did last March. That is the gap this module closes, and it is the
cheapest genuinely differentiating thing in the plan (`P31`).

    aider's note ─┐
    continue's  ─┼─→ read ─→ digest ─→ SIGNED LEDGER ENTRY
    a trailer   ─┘    │                 (digest only)
                      └──────────────→ surfaced at `inferred`,
                                        attributed to THAT TOOL

Three rules, and the value is in the restraint rather than the reach:

* **`SEC-42` — untrusted input.** A foreign record is parsed under an
  allow-list, never executed, and bounded in size. Nothing here evaluates
  anything it reads; the content is text and stays text.
* **`FR-M52-02` — somebody else's observation.** The record is labelled with
  that tool as the source and never presented as Meridian's own. It never
  rises above `inferred`, because Meridian did not see the act — it saw a
  file claiming the act happened.
* **`SEC-43` — notarising is not endorsing.** Meridian signs the *digest*.
  It does not vouch for the content, and the entry says so in as many words,
  because a signature beside a claim is read as a signature *on* the claim
  unless something stops it being read that way.

What this proves: that the record said exactly this when Meridian saw it, at
that time. What it does not: that the record was true then, or is true now.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import trailers as trailer_mod
from .gitcmd import GitTimeout, run_git_command

#: Notes refs other provenance tools write under, and the tool each belongs
#: to. A closed vocabulary for the same reason the origin vocabulary is
#: closed: "which tool said this?" must always have an answer, and a note
#: under an unrecognised ref is recorded as `unknown-tool` rather than
#: silently attributed to whichever name looked closest.
KNOWN_NOTE_REFS: dict[str, str] = {
    "refs/notes/aider": "aider",
    "refs/notes/continue": "continue",
    "refs/notes/cursor": "cursor",
    "refs/notes/devin": "devin",
    "refs/notes/gitbutler": "gitbutler",
    "refs/notes/codeium": "codeium",
    "refs/notes/sourcegraph": "sourcegraph",
    "refs/notes/commits": "git-notes",
}

#: Trailer keys other tools use to record an agent session. Values are read
#: as opaque text: a session id is somebody else's identifier and Meridian
#: has no business interpreting its structure.
KNOWN_SESSION_TRAILERS: dict[str, str] = {
    "Agent-Session-Log": "generic",
    "Aider-Session": "aider",
    "Continue-Session": "continue",
    "Cursor-Session": "cursor",
    "Devin-Session": "devin",
    "X-Codeium-Session": "codeium",
}

#: A single record is capped. A repository can carry a note of any size, and
#: a provenance reader that can be made to allocate a gigabyte by someone
#: committing one is a denial-of-service with extra steps. Oversized records
#: are recorded as truncated rather than dropped — P26, the limit is reported.
MAX_RECORD_BYTES = 64 * 1024

#: FR-M52-02. Not a default that something might raise later: there is no
#: path in this module that produces anything else. A record Meridian read
#: from a file is inferred evidence, full stop.
FOREIGN_CONFIDENCE = "inferred"

#: SEC-43, in the entry itself. A reviewer holding only the bundle reads this
#: sentence next to the signature.
NOT_ENDORSED = (
    "Meridian signed the digest of this record, not its content. The record "
    "was written by another tool; Meridian did not observe the act it "
    "describes and does not vouch for it. What the signature proves is that "
    "the record said exactly this when Meridian read it."
)


class InteropError(Exception):
    """A foreign record that could not be read. Never raised for a record
    that is merely absent — a repository with no notes is the normal case."""


@dataclass(frozen=True)
class ForeignRecord:
    """One provenance record written by something that is not Meridian."""

    tool: str
    #: `git-note` or `trailer`.
    kind: str
    #: The notes ref, or the trailer key.
    source: str
    commit: str
    content: str
    #: `sha256:…` over the exact bytes read, before any parsing.
    digest: str
    observed_at: str
    truncated: bool = False

    @property
    def confidence(self) -> str:
        """Always `inferred`. A property rather than a field so no caller can
        construct a `ForeignRecord` that claims to have been observed
        directly (`FR-M52-02`)."""
        return FOREIGN_CONFIDENCE

    def as_wire(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "kind": self.kind,
            "source": self.source,
            "commit": self.commit,
            "digest": self.digest,
            "observedAt": self.observed_at,
            "confidence": self.confidence,
            "truncated": self.truncated,
            "notEndorsed": NOT_ENDORSED,
        }


def digest_of_bytes(raw: bytes) -> str:
    """The digest that gets signed, over exact bytes.

    No normalisation of any kind. A reader re-deriving this later has to get
    the same answer from the same bytes, and any tidying — stripping trailing
    whitespace, normalising newlines — would make a record that *had* been
    altered digest identically, which is the one thing this must never do.
    """
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def digest_of(content: str) -> str:
    """The digest of text, as UTF-8. Used for trailers, which are read out of
    a commit message and are text by the time anyone sees them."""
    return digest_of_bytes(content.encode("utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_note_refs(repo: Path | str) -> list[str]:
    """Notes refs present in this repository, recognised or not."""
    result = run_git_command(
        repo, "for-each-ref", "--format=%(refname)", "refs/notes/"
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def read_foreign_notes(
    repo: Path | str,
    *,
    refs: list[str] | None = None,
    now: Any = None,
) -> list[ForeignRecord]:
    """Every foreign provenance note in this repository.

    Meridian's own ref is skipped: notarising our own record would be
    circular and would put a second, weaker copy of something already in the
    ledger beside it.

    A ref that cannot be read is skipped rather than raised. A repository
    carrying one broken note should still yield the others; refusing the lot
    would mean one bad note hides every good one.
    """
    stamp = (now or _now)()
    found: list[ForeignRecord] = []
    for ref in refs if refs is not None else list_note_refs(repo):
        if ref.startswith("refs/notes/meridian"):
            continue
        tool = KNOWN_NOTE_REFS.get(ref, "unknown-tool")
        try:
            listing = run_git_command(repo, "notes", "--ref", ref, "list")
        except GitTimeout:
            continue
        if listing.returncode != 0:
            continue
        for line in listing.stdout.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            blob, commit = parts
            # `cat-file blob`, not `notes show`. `show` is a presentation
            # command and adds a trailing newline of its own; digesting its
            # output would mean a git upgrade that changed that formatting
            # made every notarised record read as altered. The blob is the
            # bytes the other tool actually stored.
            try:
                shown = run_git_command(repo, "cat-file", "blob", blob, text=False)
            except GitTimeout:
                continue
            if shown.returncode != 0:
                continue
            raw: bytes = shown.stdout
            truncated = False
            if len(raw) > MAX_RECORD_BYTES:
                raw = raw[:MAX_RECORD_BYTES]
                truncated = True
            found.append(
                ForeignRecord(
                    tool=tool,
                    kind="git-note",
                    source=ref,
                    commit=commit,
                    content=raw.decode("utf-8", errors="replace"),
                    digest=digest_of_bytes(raw),
                    observed_at=stamp,
                    truncated=truncated,
                )
            )
    return found


def read_foreign_trailers(
    repo: Path | str,
    commit: str,
    *,
    now: Any = None,
) -> list[ForeignRecord]:
    """Session-log and co-author trailers on one commit.

    Uses the sidecar's single trailer parser (`trailers.py`) rather than a
    second regex, because two trailer implementations drift and the one that
    drifts is the one nobody is reading.
    """
    stamp = (now or _now)()
    result = run_git_command(repo, "log", "-1", "--format=%B", commit)
    if result.returncode != 0:
        return []
    message = result.stdout
    records: list[ForeignRecord] = []

    for key, value in trailer_mod.parse_trailers(message):
        if key in KNOWN_SESSION_TRAILERS:
            records.append(
                ForeignRecord(
                    tool=KNOWN_SESSION_TRAILERS[key],
                    kind="trailer",
                    source=key,
                    commit=commit,
                    content=value,
                    digest=digest_of(value),
                    observed_at=stamp,
                )
            )

    for attribution in trailer_mod.parse_attributions(message):
        # Meridian's own line is already in the ledger; notarising it would
        # be Meridian vouching for Meridian.
        if attribution.get("meridianAuthored"):
            continue
        vendor = attribution.get("vendor") or "unknown"
        if vendor in {"generic", "unknown"}:
            # A human co-author is not another tool's provenance record.
            continue
        value = f"{attribution.get('name')} <{attribution.get('email')}>"
        records.append(
            ForeignRecord(
                tool=vendor,
                kind="trailer",
                source=trailer_mod.CO_AUTHORED_BY_KEY,
                commit=commit,
                content=value,
                digest=digest_of(value),
                observed_at=stamp,
            )
        )
    return records


def parsed_payload(record: ForeignRecord) -> dict[str, Any]:
    """What the record says, insofar as it can be read safely.

    JSON is parsed because `json.loads` is a parser and not an evaluator, and
    a structured note is more useful to a reader than a blob. Anything else
    stays text. Nothing is ever executed, imported, or interpreted as a path
    to open — `SEC-42`.

    A record that does not parse is not an error. It is a record in a format
    Meridian does not read, which is exactly what should be expected of a
    format somebody else owns and may change.
    """
    text = record.content.strip()
    if not text.startswith("{") and not text.startswith("["):
        return {"format": "text", "parsed": False}
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return {"format": "text", "parsed": False}
    if isinstance(value, dict):
        # Only scalar leaves are surfaced. A nested structure from an
        # untrusted file is where a surface ends up rendering something
        # nobody designed for.
        flat = {
            str(key): item
            for key, item in value.items()
            if isinstance(item, (str, int, float, bool)) or item is None
        }
        return {"format": "json", "parsed": True, "fields": flat}
    return {"format": "json", "parsed": True, "fields": {}}


def notarisation_entry(record: ForeignRecord) -> dict[str, Any]:
    """The ledger entry that makes a foreign record tamper-evident.

    The digest goes in; the content does not, and neither does anything
    parsed out of the content. That is the difference between notarising and
    copying: Meridian is not the custodian of another tool's data, and taking
    a copy — even a tidy, structured, partial one — would make it one, with
    the retention, erasure and disclosure obligations that follow.

    `parsed_payload` exists for the read path, where a surface shows a person
    what is in their own repository. It is deliberately not here. The first
    version of this function included it, and the test that says the content
    is not copied caught it: a "fields" map of scalars pulled out of the note
    is the note, rearranged.
    """
    return {
        "storyId": f"interop/{record.tool}",
        "phase": "operate",
        "actionType": "foreign_record_notarised",
        "vendor": record.tool,
        "observationConfidence": record.confidence,
        "decision": None,
        "detail": dict(record.as_wire()),
    }


@dataclass(frozen=True)
class NotarisationVerdict:
    """Whether a notarised record still says what it said."""

    ok: bool
    digest_at_notarisation: str
    digest_now: str | None
    detail: str


def verify_notarisation(
    notarised_digest: str,
    record_now: ForeignRecord | None,
) -> NotarisationVerdict:
    """`AC-59`'s second half: has the record changed since Meridian saw it?

    A record that has vanished is reported as gone rather than as altered.
    They are different events — a tool cleaning up its own notes is ordinary,
    and accusing it of tampering would make this check the boy who cried
    wolf.
    """
    if record_now is None:
        return NotarisationVerdict(
            ok=False,
            digest_at_notarisation=notarised_digest,
            digest_now=None,
            detail=(
                "The record that was notarised is no longer in the repository. "
                "The ledger entry still proves it existed and what it said; it "
                "cannot say who removed it."
            ),
        )
    if record_now.digest == notarised_digest:
        return NotarisationVerdict(
            ok=True,
            digest_at_notarisation=notarised_digest,
            digest_now=record_now.digest,
            detail="Unchanged since Meridian notarised it.",
        )
    return NotarisationVerdict(
        ok=False,
        digest_at_notarisation=notarised_digest,
        digest_now=record_now.digest,
        detail=(
            f"This record has been altered since Meridian notarised it. "
            f"It digested {notarised_digest} when it was recorded and "
            f"{record_now.digest} now. The ledger entry is signed, so what "
            f"changed is the record in the repository, not Meridian's copy "
            f"of its digest."
        ),
    )
