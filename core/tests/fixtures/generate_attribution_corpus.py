"""Generator for the labelled attribution corpus (FR-M41-03, AC-42;
N1 Workstream B T11).

Run once (and re-run only to extend the corpus, never to patch a red
evaluation):

    python core/tests/fixtures/generate_attribution_corpus.py

The corpus is synthetic-but-realistic: every span is constructed in code
with a FIXED SEED, and its label is fixed by the documented contract of
:class:`meridian_core.attribution.spans.classify_span` — the precedence
(excluded > agent trailer > formatter sweep > squash merge > author bot
marker > human author > pre-installation/no-signal) applied to the
span's own evidence, with vendor support resolved through the same
VENDOR_EMAILS table. A small share of ADVERSARIAL spans (humans named
like vendors, humans with bot-like emails) carries judgement labels that
a naive classifier would miss — those keep the published precision
figures honest rather than tautological.

The generated JSON is COMMITTED: the evaluation test
(tests/test_attribution_corpus.py) reads the fixture, so the published
figures are reproducible from the repository alone.

Zero model calls (FR-M36-07): pools, jitter and integer arithmetic.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 41
INSTALL_T = "2025-01-01T00:00:00Z"
PRE_INSTALL_T = "2023-06-15T09:30:00+00:00"
POST_INSTALL_T = "2025-06-20T14:45:00+00:00"

HUMAN_NAMES = [
    ("Alice A", "alice@example.com"),
    ("Bob B", "bob@example.com"),
    ("Carol C", "carol@example.org"),
    ("Dana D", "dana.d@example.net"),
    ("Erik E", "erik@corp.example.com"),
]

# Adversarial: humans whose names collide with vendor names or whose
# emails look bot-ish. Truth: human — a classifier that matches vendor
# names without bot markers would overclaim agent here.
ADVERSARIAL_HUMANS = [
    ("Claude Martin", "claude@example.com"),
    ("Copeland Young", "copilot.young@example.com"),
    ("Devin Hester", "devin@example.com"),
    ("Roberta Botkin", "roberta@example.com"),
    ("A. Codex", "a.codex@example.com"),
]

AGENT_TRAILERS = [
    "Co-Authored-By: Claude <noreply@anthropic.com>",
    "Co-Authored-By: GitHub Copilot <copilot@github.com>",
    "Co-Authored-By: Cursor <cursor@anysphere.inc>",
    "Co-Authored-By: Codex <codex@openai.com>",
    "Co-Authored-By: Devin <devin-ai-integration[bot]@users.noreply.github.com>",
    "Co-Authored-By: Pair Agent <pair-agent@example.com>",  # generic vendor
]

SUPPORTED_BOT_AUTHORS = [
    ("copilot[bot]", "copilot@github.com"),
    ("anthropic-claude[bot]", "noreply@anthropic.com"),
    ("cursor-agent[bot]", "cursor@cursor.com"),
    ("openai-codex[bot]", "codex@openai.com"),
]

UNSUPPORTED_BOT_AUTHORS = [
    ("speedbot[bot]", "speedbot@bots.example.com"),
    ("dependabot[bot]", "dependabot@dependabot.com"),
    ("buildomat[bot]", "buildomat@ci.example.org"),
]

FORMATTER_SUBJECTS = [
    "chore: run black",
    "Reformat sources",
    "style: format",
    "prettier sweep",
    "lint: whitespace-only",
    "chore(tools): run isort",
    "run gofmt",
]

SQUASH_SUBJECTS = [
    "Feature branch work (#142)",
    "Paydown the tech-debt list (#87)",
    "Squashed commit of the following:\n\ncommit a1\ncommit b2",
]

HUMAN_SUBJECTS = [
    "fix the off-by-one in the pager",
    "add retry backoff to the connector",
    "review follow-ups",
    "document the envelope semantics",
    "hand-tuned fixture timestamps",
]


def _pick(rng: random.Random, pool: list):
    return pool[rng.randrange(len(pool))]


def build_spans() -> list[dict]:
    rng = random.Random(SEED)
    spans: list[dict] = []
    counter = 0

    def add(author, message, when, state, confidence, *, excluded=False):
        nonlocal counter
        counter += 1
        spans.append(
            {
                "id": f"span-{counter:04d}",
                "authorName": author[0],
                "authorEmail": author[1],
                "message": message,
                "authorTime": when,
                "excluded": excluded,
                "expectedState": state,
                "expectedConfidence": confidence,
            }
        )

    # Agent evidence: trailers, post-installation -> agent/observed (40).
    for _ in range(40):
        author = _pick(rng, HUMAN_NAMES)
        add(author, f"agent work\n\n{_pick(rng, AGENT_TRAILERS)}\n",
            POST_INSTALL_T, "agent", "observed")

    # Agent evidence: trailers on pre-installation commits -> agent, but
    # FR-M41-16 says inferred, never observed (12).
    for _ in range(12):
        author = _pick(rng, HUMAN_NAMES)
        add(author, f"old agent work\n\n{_pick(rng, AGENT_TRAILERS)}\n",
            PRE_INSTALL_T, "agent", "inferred")

    # Agent evidence: supported author bot markers (18).
    for _ in range(18):
        author = _pick(rng, SUPPORTED_BOT_AUTHORS)
        add(author, _pick(rng, HUMAN_SUBJECTS), POST_INSTALL_T, "agent", "observed")

    # Human evidence: plain authors, post-installation (45).
    for _ in range(45):
        author = _pick(rng, HUMAN_NAMES)
        add(author, _pick(rng, HUMAN_SUBJECTS), POST_INSTALL_T, "human", "observed")

    # Human evidence: plain authors predating installation -> human at
    # inferred confidence (FR-M41-16) (15).
    for _ in range(15):
        author = _pick(rng, HUMAN_NAMES)
        add(author, _pick(rng, HUMAN_SUBJECTS), PRE_INSTALL_T, "human", "inferred")

    # Adversarial humans: names collide with vendors, emails look bot-ish
    # — truth stays human (12).
    for _ in range(12):
        author = _pick(rng, ADVERSARIAL_HUMANS)
        add(author, _pick(rng, HUMAN_SUBJECTS), POST_INSTALL_T, "human", "observed")

    # Unattributed: formatter sweeps (16).
    for _ in range(16):
        author = _pick(rng, HUMAN_NAMES)
        add(author, _pick(rng, FORMATTER_SUBJECTS), POST_INSTALL_T,
            "unattributed", "inferred")

    # Unattributed: squash merges (14).
    for _ in range(14):
        author = _pick(rng, HUMAN_NAMES)
        add(author, _pick(rng, SQUASH_SUBJECTS), POST_INSTALL_T,
            "unattributed", "inferred")

    # Unattributed: unsupported bot vendors (12).
    for _ in range(12):
        author = _pick(rng, UNSUPPORTED_BOT_AUTHORS)
        add(author, _pick(rng, HUMAN_SUBJECTS), POST_INSTALL_T,
            "unattributed", "inferred")

    # Unattributed: pre-installation with no surviving signal (8).
    for _ in range(8):
        add(("unknown", ""), "", PRE_INSTALL_T, "unattributed", "inferred")

    # Unattributed: no signal at all, post-installation (6).
    for _ in range(6):
        add(("unknown", ""), "", POST_INSTALL_T, "unattributed", "unknown")

    # Unattributed: excluded paths — reported, never silently dropped (8).
    for _ in range(8):
        author = _pick(rng, HUMAN_NAMES + SUPPORTED_BOT_AUTHORS)
        add(author, _pick(rng, HUMAN_SUBJECTS), POST_INSTALL_T,
            "unattributed", "unknown", excluded=True)

    return spans


def main() -> None:
    spans = build_spans()
    corpus = {
        "version": 1,
        "vocabularyVersion": 1,
        "contractVersion": "attrib-provenance/v1",
        "seed": SEED,
        "installedAt": INSTALL_T,
        "size": len(spans),
        "spans": spans,
    }
    out = Path(__file__).with_name("attribution_corpus.json")
    out.write_text(
        json.dumps(corpus, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {out} with {len(spans)} spans")


if __name__ == "__main__":
    main()
