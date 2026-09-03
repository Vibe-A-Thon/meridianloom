"""SEC-07: secret-redaction filter applied before anything is persisted.

Every input/output written to the blob store passes through this filter
first. The pattern set is deliberately conservative: known credential
shapes and explicit key/value assignments. A false positive redacts a
long word; a false negative leaks a secret — the asymmetry favours
over-redaction.

Known-credential shapes are matched by provider prefix; the generic
assignment pattern catches `api_key: …`, `token = "…"`, `password=…` and
friends. Redaction rewrites the value, so the digest in the ledger entry
is the digest of the redacted ciphertext.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # PEM private key blocks (multi-line).
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
            r".*?"
            r"-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED-PRIVATE-KEY]",
    ),
    # AWS access key ids.
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),
    # GitHub tokens (classic + fine-grained PAT).
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), REDACTED),
    # Slack tokens.
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), REDACTED),
    # OpenAI-style keys.
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), REDACTED),
    # Explicit assignments: api_key, access_token, auth_token, secret,
    # password, client_secret — value redacted, key/quoting preserved.
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|"
            r"password|client[_-]?secret)\b(\s*[:=]\s*)(['\"]?)"
            r"[\w\-./+=]{8,}\3"
        ),
        r"\1\2\3" + REDACTED + r"\3",
    ),
]


def redact_secrets(text: str) -> str:
    """Return `text` with any detected credential material redacted."""
    redacted = text
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
