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
    for pattern, replacement in [*_PATTERNS, *_EXTRA_PATTERNS]:
        redacted = pattern.sub(replacement, redacted)
    return redacted


# -- FR-M43-06 (N2 Workstream D task 17): profile- and field-level redaction --

#: Runtime-registered patterns (FR-M43-06 field redaction): an operator
#: or test can register organisation-specific secret shapes without
#: editing this file. Applied after the built-in set, same asymmetry:
#: over-redaction is preferred over a leak.
_EXTRA_PATTERNS: list[tuple[re.Pattern[str], str]] = []


def register_redaction_pattern(pattern: str, replacement: str = REDACTED) -> None:
    """Register an extra credential shape, e.g. an org-specific token
    prefix. Idempotent: registering the same pattern twice is a no-op."""
    compiled = re.compile(pattern)
    if all(existing.pattern != compiled.pattern for existing, _ in _EXTRA_PATTERNS):
        _EXTRA_PATTERNS.append((compiled, replacement))


def clear_registered_patterns() -> None:
    """Drop all runtime-registered patterns (test isolation)."""
    _EXTRA_PATTERNS.clear()


def _set_path(value: Any, parts: list[str], replacement: str) -> bool:
    """Set the value at a dotted path (``tool_calls.0.command``) inside
    nested dicts/lists to `replacement`; False when the path does not
    exist."""
    if not parts:
        return False
    head, *tail = parts
    if isinstance(value, list) and head.isdigit():
        index = int(head)
        if index >= len(value):
            return False
        if not tail:
            value[index] = replacement
            return True
        return _set_path(value[index], tail, replacement)
    if isinstance(value, dict) and head in value:
        if not tail:
            value[head] = replacement
            return True
        return _set_path(value[head], tail, replacement)
    return False


def redact_fields(payload: dict, fields: set[str]) -> dict:
    """FR-M43-06 field and path redaction: return a copy of `payload`
    with each named top-level field — or dotted path into nested
    dicts/lists — replaced by ``[REDACTED]``. Unknown fields are left
    untouched (a redaction request for data that is not there is a
    no-op, not an error)."""
    import copy

    out = copy.deepcopy(payload)
    for field in fields:
        parts = field.split(".")
        if len(parts) == 1:
            if field in out and out[field] is not None:
                out[field] = REDACTED
            continue
        _set_path(out, parts, REDACTED)
    return out
