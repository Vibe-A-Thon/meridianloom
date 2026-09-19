"""The licence manager the sidecar consults on every request.

It finds licence files, verifies them, evaluates them against this machine
and the developer's git identity, and answers one question quickly: *may this
method run?*  The answer is re-derived from cached, already-verified licences
at most every five minutes, so an expiring licence starts its grace period
without a restart and a newly installed one is noticed without a reload.

No network access. No writes except ``install`` / ``remove``, which are the
explicit user actions.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..childenv import child_environment
from . import editions, keys, machine, store
from .licence import (
    ACTIVE_STATES,
    NO_LICENCE,
    STATE_GRACE,
    STATE_INVALID,
    STATE_VALID,
    STATE_WRONG_DEVELOPER,
    Licence,
    LicenceError,
    LicenceStatus,
    TrustedKey,
    evaluate,
    parse_and_verify,
)

#: How long a computed status is reused before the files are looked at again.
REFRESH_SECONDS = 300.0

#: Statuses preferred when several licences are present.
_RANK = {STATE_VALID: 0, STATE_GRACE: 1}


def git_developer_emails(workspace_dir: str | None) -> frozenset[str]:
    """The developer identity, as git sees it: ``user.email`` for the
    workspace (repository, then global config). This is *asserted* identity —
    the same D9/D38 position as the rest of the product — so a per-developer
    licence is a named-user entitlement backed by the licence agreement, not a
    cryptographic proof of who is typing."""
    commands = []
    if workspace_dir and Path(workspace_dir).is_dir():
        commands.append(["git", "-C", workspace_dir, "config", "--get", "user.email"])
    commands.append(["git", "config", "--global", "--get", "user.email"])
    emails: set[str] = set()
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                env=child_environment(),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        value = (completed.stdout or "").strip().lower()
        if completed.returncode == 0 and value:
            emails.add(value)
            break  # the first (most specific) answer is the effective identity
    return frozenset(emails)


class LicenceManager:
    def __init__(
        self,
        *,
        workspace_dir: str | None = None,
        clock: Callable[[], datetime] | None = None,
        trusted: dict[str, TrustedKey] | None = None,
        revoked_key_ids: frozenset[str] | None = None,
        user_dir: Path | None = None,
        machine_dir: Path | None = None,
        fingerprint: Callable[[], str | None] | None = None,
        developer_emails: Callable[[str | None], frozenset[str]] | None = None,
        fixed_status: LicenceStatus | None = None,
    ) -> None:
        self._workspace_dir = workspace_dir
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._trusted = trusted
        self._revoked = keys.REVOKED_KEY_IDS if revoked_key_ids is None else revoked_key_ids
        self._user_dir = user_dir
        self._machine_dir = machine_dir
        self._fingerprint = fingerprint or machine.machine_fingerprint
        self._developer_emails = developer_emails or git_developer_emails
        self._fixed = fixed_status
        self._status: LicenceStatus | None = None
        self._loaded_at = 0.0

    # -- status ---------------------------------------------------------

    def _trust(self) -> dict[str, TrustedKey]:
        return self._trusted if self._trusted is not None else keys.trusted_keys()

    def _files(self) -> list[Path]:
        return store.candidate_files(self._user_dir, self._machine_dir)

    def _compute(self) -> LicenceStatus:
        if self._fixed is not None:
            return self._fixed
        files = self._files()
        if not files:
            # The Community default: no files, so no need to read the machine
            # id or shell out to git for an identity nothing will consult.
            return NO_LICENCE
        trust = self._trust()
        fingerprint = self._fingerprint()
        emails = self._developer_emails(self._workspace_dir)
        now = self._clock()
        results: list[LicenceStatus] = []
        checked: list[str] = []
        for path in files:
            try:
                text = path.read_bytes()
            except OSError as error:
                results.append(LicenceStatus(STATE_INVALID, f"cannot read {path}: {error.strerror or error}", None, str(path)))
                checked.append(f"{path}: unreadable")
                continue
            try:
                licence = parse_and_verify(text, trust, self._revoked)
            except LicenceError as error:
                results.append(LicenceStatus(error.state, str(error), None, str(path)))
                checked.append(f"{path}: {error.state}")
                continue
            status = evaluate(
                licence, now=now, machine_fingerprint=fingerprint,
                developer_emails=emails, source=str(path),
            )
            results.append(status)
            checked.append(f"{path}: {status.state}")
        if not results:
            return NO_LICENCE
        # Valid beats grace beats everything else; ties keep discovery order
        # (explicit file, then user directory, then machine directory).
        best = min(results, key=lambda s: _RANK.get(s.state, 9))
        return LicenceStatus(
            best.state, best.reason, best.licence, best.source, best.days_remaining, tuple(checked)
        )

    def reload(self, workspace_dir: str | None = None) -> LicenceStatus:
        if workspace_dir:
            self._workspace_dir = workspace_dir
        self._status = self._compute()
        self._loaded_at = time.monotonic()
        return self._status

    @property
    def status(self) -> LicenceStatus:
        if self._fixed is not None:
            return self._fixed
        if self._status is None or time.monotonic() - self._loaded_at > REFRESH_SECONDS:
            self.reload()
        assert self._status is not None
        return self._status

    # -- enforcement ----------------------------------------------------

    def check_method(self, method: str) -> dict[str, Any] | None:
        """None when ``method`` may run; otherwise the refusal payload."""
        feature = editions.required_feature(method)
        if feature is None:
            return None
        status = self.status
        if status.grants(feature):
            return None
        if status.premium_active:
            reason = (
                f"the installed licence ({status.licence.licence_id if status.licence else '?'}) "
                f"does not include the {feature!r} feature"
            )
        else:
            reason = status.reason
        return {
            "message": f"{method} is a Meridian Loom Premium feature ({feature}). {reason}",
            "data": {
                "method": method,
                "feature": feature,
                "edition": "community",
                "licenceState": status.state,
                "remediation": (
                    "Install a Premium licence key: run 'Meridian: Install Licence' in VS Code, "
                    "or 'meridian licence install <file>'. Trial and purchase details: LICENSING.md."
                ),
            },
        }

    # -- user actions ---------------------------------------------------

    def install(self, text: str, scope: str = store.SCOPE_USER) -> LicenceStatus:
        """Verify then store a licence. Refuses anything that would not
        unlock premium features here, so a wrong file fails at install time
        with a reason instead of silently not working later."""
        licence = parse_and_verify(text, self._trust(), self._revoked)  # raises LicenceError
        emails = self._developer_emails(self._workspace_dir)
        status = evaluate(
            licence, now=self._clock(), machine_fingerprint=self._fingerprint(),
            developer_emails=emails,
        )
        identity_unknown = status.state == STATE_WRONG_DEVELOPER and not emails
        if status.state not in ACTIVE_STATES and not identity_unknown:
            raise LicenceError(status.state, status.reason)
        directory = store.scope_dir(scope, self._user_dir, self._machine_dir)
        path = store.write_licence(text if text.endswith("\n") else text + "\n", licence.licence_id, directory)
        self.reload()
        result = self.status
        if identity_unknown:
            return LicenceStatus(
                result.state, result.reason + " (Set git user.email so the named developer can be matched.)",
                result.licence, str(path), result.days_remaining, result.checked,
            )
        return result

    def remove(self, scope: str = store.SCOPE_USER) -> list[str]:
        directory = store.scope_dir(scope, self._user_dir, self._machine_dir)
        removed = [str(p) for p in store.remove_licences(directory)]
        self.reload()
        return removed


# -- process-wide default, with a hook for the test suite --------------------

_TEST_STATUS: LicenceStatus | None = None


def set_test_status(status: LicenceStatus | None) -> None:
    """Make every manager created by :func:`new_manager` report ``status``.
    Used by the test suite so the many existing tests of Premium methods
    need not each mint a licence; ``None`` restores real behaviour."""
    global _TEST_STATUS
    _TEST_STATUS = status


def new_manager(**kwargs: Any) -> LicenceManager:
    if _TEST_STATUS is not None and "fixed_status" not in kwargs:
        kwargs["fixed_status"] = _TEST_STATUS
    return LicenceManager(**kwargs)


def premium_test_status() -> LicenceStatus:
    """An all-features Premium status for tests."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    licence = Licence(
        licence_id="ML-TEST", licensee_name="Test Suite", licensee_contact="",
        kind="machine", developers=(), machines=("*",), seats=1, features=("*",),
        issued_at=now, not_before=None, expires_at=now + timedelta(days=3650),
        trial=False, key_id="ml-dev", development_key=True,
    )
    return LicenceStatus(STATE_VALID, "test suite premium licence", licence, "test")
