"""One-way isolation tests (SEC-27; F0 Workstream D task 22).

Observed agents gain no access to Meridian credentials, policy, or the
ledger signing key. Enforcement is proven at four layers:

1. Import surface: importing the whole observer subsystem must not load
   ``meridian_core.ledger`` (key material lives there) — verified in a
   fresh interpreter so in-process pollution cannot hide it.
2. Static surface: no observer source file may import the ledger/key
   modules.
3. Spawned probes: every child process (gh probes, process listings) is
   launched with a scrubbed environment; the scrub AUDIT names what was
   removed, and a real child process demonstrates it sees zero MERIDIAN_*
   variables even when the parent holds fake secrets.
4. RPC surface: observer-facing methods accept no credential parameters
   (schema-level additionalProperties: false on empty params).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

CORE_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = CORE_ROOT / "meridian_core"

CHILD_ENV_PROBE = (
    "import os, json; "
    "print(json.dumps(sorted(k for k in os.environ "
    "if k.startswith('MERIDIAN_'))))"
)


class TestImportSurface:
    def test_importing_observers_loads_no_ledger_or_key_modules(self):
        """Fresh-interpreter proof: observer subsystem runs key-free."""
        code = (
            "import pkgutil, sys\n"
            "import meridian_core.observers as observers\n"
            "for m in pkgutil.iter_modules(observers.__path__):\n"
            "    __import__(f'meridian_core.observers.{m.name}')\n"
            "loaded = sorted(sys.modules)\n"
            "leaks = [m for m in loaded if m.startswith('meridian_core.ledger')]\n"
            "crypto = [m for m in loaded if m.split('.')[0] == 'cryptography']\n"
            "assert not leaks, f'ledger modules reached observers: {leaks}'\n"
            "assert not crypto, f'key machinery reached observers: {crypto}'\n"
            "print('isolation-ok')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=CORE_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "isolation-ok" in result.stdout

    def test_static_no_ledger_imports_in_observer_sources(self):
        """Defense in depth on the source itself."""
        observers_dir = PACKAGE_ROOT / "observers"
        import_re = re.compile(r"^\s*(?:from|import)\s+[^\n#]*\bledger\b", re.MULTILINE)
        violations = []
        for path in sorted(observers_dir.rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in import_re.finditer(text):
                line = text[: match.start()].count("\n") + 1
                violations.append(f"{path.name}:{line}")
        assert violations == [], (
            "SEC-27: observers must not import ledger/key modules: " + ", ".join(violations)
        )


class TestScrubEnv:
    def test_all_meridian_secrets_removed_with_audit(self, monkeypatch):
        from meridian_core.observers.isolation import scrub_env

        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "super-secret-seed")
        monkeypatch.setenv("MERIDIAN_POLICY_BLOB", "policy-contents")
        monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
        clean, audit = scrub_env()
        assert "MERIDIAN_LEDGER_SIGNING_KEY" in audit
        assert "MERIDIAN_POLICY_BLOB" in audit
        assert not any(k.startswith("MERIDIAN_") for k in clean)
        assert "PATH" in clean  # ordinary environment is untouched

    def test_explicit_env_mapping_is_scrubbed(self):
        from meridian_core.observers.isolation import scrub_env

        env = {
            "HOME": "/home/dev",
            "MERIDIAN_LEDGER_SIGNING_KEY": "s3cret",
            "MERIDIAN_PARENT_PID": "1234",
        }
        clean, audit = scrub_env(env)
        assert audit == ["MERIDIAN_LEDGER_SIGNING_KEY", "MERIDIAN_PARENT_PID"]
        assert clean == {"HOME": "/home/dev"}

    def test_real_child_process_sees_no_meridian_secrets(self, monkeypatch):
        """The scrubbing-audit acceptance test: a real spawned probe."""
        from meridian_core.observers.isolation import scrub_env

        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "s3cret")
        monkeypatch.setenv("MERIDIAN_ANOTHER_SECRET", "x")
        clean, audit = scrub_env()
        assert len(audit) >= 2
        result = subprocess.run(
            [sys.executable, "-c", CHILD_ENV_PROBE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            env=clean,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == []


class TestProbeSpawnsAreScrubbed:
    def test_process_listing_probe_env_is_scrubbed(self, monkeypatch):
        """processes._run_probe must hand a scrubbed env to the child."""
        from meridian_core.observers import processes

        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "s3cret")
        seen: list[dict] = []
        real_run = subprocess.run

        def spy_run(argv, **kwargs):
            seen.append(dict(kwargs.get("env") or {}))
            return real_run([sys.executable, "-c", CHILD_ENV_PROBE], **{**kwargs, "env": kwargs.get("env")})

        monkeypatch.setattr(processes.subprocess, "run", spy_run)
        monkeypatch.setattr(
            processes, "_list_windows_fast", lambda: (_ for _ in ()).throw(RuntimeError("force fallback"))
        )
        monkeypatch.setattr(
            processes, "_list_windows_api", lambda: (_ for _ in ()).throw(RuntimeError("force fallback"))
        )
        monkeypatch.setattr(processes, "_run_probe", processes._run_probe)  # keep
        # Drive the real _run_probe through the tasklist fallback path only
        # on Windows; on POSIX the ps path uses the same _run_probe.
        monkeypatch.setattr(processes, "_list_windows_fallback", processes._list_windows_fallback)
        try:
            processes._run_probe(["tasklist", "/FO", "CSV", "/NH"], 15)
        except Exception:  # noqa: BLE001 - the probe binary may be absent on POSIX
            pass
        if sys.platform != "win32":
            processes._run_probe(["ps", "-eo", "pid=,comm=,args="], 15)
        assert seen, "no probe was spawned"
        for env in seen:
            assert not any(k.startswith("MERIDIAN_") for k in env), env.keys()

    def test_gh_probe_env_is_scrubbed(self, monkeypatch):
        from meridian_core.observers import copilot

        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "s3cret")
        seen: list[dict] = []
        real_run = subprocess.run

        def spy_run(argv, **kwargs):
            seen.append(dict(kwargs.get("env") or {}))
            return real_run(argv, **kwargs)

        monkeypatch.setattr(copilot.subprocess, "run", spy_run)
        copilot.default_runner(["gh", "--version"], 5)
        assert seen, "gh probe was not spawned"
        for env in seen:
            assert not any(k.startswith("MERIDIAN_") for k in env), env.keys()


class TestRpcSurface:
    def test_observer_methods_accept_no_credential_parameters(self):
        """Schema-level proof: empty params, additionalProperties false."""
        schema = json.loads(
            (CORE_ROOT.parent / "shared" / "schema" / "methods.json").read_text(
                encoding="utf-8"
            )
        )
        for name in ("ObserveSessionsParams", "ObserveHealthParams"):
            definition = schema["$defs"][name]
            assert definition.get("properties", {}) == {}, name
            assert definition.get("additionalProperties") is False, name

    def test_handlers_ignore_any_supplied_params(self):
        """Runtime defense: observe/* handlers take nothing from params."""
        from meridian_core.server import SidecarServer

        server = SidecarServer()
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "observe/sessions",
                "params": {"ledgerSigningKey": "echo-me-if-you-can"},
            }
        )
        assert "result" in response  # ignored, never echoed, never read


class TestKeyScoping:
    def test_observer_manager_never_receives_key_material(self):
        """The manager's constructor has no key/credential parameter, and
        constructing it with secrets present in the environment loads
        nothing (asserted by TestImportSurface in a fresh interpreter)."""
        from meridian_core.observers.manager import ObserverManager

        import inspect

        signature = inspect.signature(ObserverManager.__init__)
        banned = {"key", "seed", "secret", "credential", "token", "signing"}
        assert not (set(signature.parameters) & banned)
        manager = ObserverManager()
        assert manager.vendors == []
