"""Doctor check registry tests (FR-M30-01).

Every check's pass and non-pass paths are proven; the not-yet-built
subsystems (ledger, signing key, observers, trailer hook) must report a clear
not-installed status with remediation rather than crash.
"""

from __future__ import annotations

import sys
import time

import pytest

import bus_types
from meridian_core import doctor, protocol
from meridian_core.server import SidecarServer


def make_context(**overrides) -> doctor.DoctorContext:
    return doctor.DoctorContext(started_at=time.monotonic(), **overrides)


def by_id(result: bus_types.DoctorRunResult, check_id: str) -> bus_types.DoctorCheck:
    for check in result["checks"]:
        if check["id"] == check_id:
            return check
    raise AssertionError(f"check {check_id} missing from {result['checks']}")


class TestRegistry:
    def test_registry_covers_the_fr_m30_01_check_set(self):
        # FR-M30-01 (as scoped by F0-A task 6): interpreter, sidecar,
        # keychain (signing key host-side + provisioning here), ledger
        # integrity, git hooks, observer health.
        assert doctor.check_ids() == [
            "interpreter",
            "sidecar",
            "signing-key",
            "ledger",
            "git-hooks",
            "observers",
        ]

    def test_every_result_matches_the_generated_contract_shape(self):
        result = doctor.run_doctor({}, make_context())
        for check in result["checks"]:
            assert set(check) <= {"id", "name", "status", "detail", "remediation"}
            assert check["status"] in ("pass", "warn", "fail")
            assert check["detail"]
            if check["status"] != "pass":
                # Actionable results (FR-M30-01): every non-pass check says
                # what to do about it.
                assert check["remediation"]


class TestInterpreterCheck:
    def test_pass_on_this_interpreter(self):
        check = by_id(doctor.run_doctor({"checks": ["interpreter"]}, make_context()), "interpreter")
        assert check["status"] == "pass"
        assert sys.version_info[0] >= 3
        assert "Python" in check["detail"]

    def test_fail_when_too_old(self, monkeypatch):
        monkeypatch.setattr(
            doctor, "_interpreter_info", lambda: (sys.executable, (3, 9, 0))
        )
        check = by_id(doctor.run_doctor({}, make_context()), "interpreter")
        assert check["status"] == "fail"
        assert "too old" in check["detail"]
        assert "meridian.python.interpreterPath" in check["remediation"]

    def test_fail_when_executable_missing(self, monkeypatch, tmp_path):
        ghost = str(tmp_path / "no-such-python")
        monkeypatch.setattr(doctor, "_interpreter_info", lambda: (ghost, (3, 11, 9)))
        check = by_id(doctor.run_doctor({}, make_context()), "interpreter")
        assert check["status"] == "fail"
        assert ghost in check["detail"]


class TestSidecarCheck:
    def test_pass_reports_pid_and_protocol(self):
        check = by_id(doctor.run_doctor({}, make_context()), "sidecar")
        assert check["status"] == "pass"
        assert "pid" in check["detail"]
        assert f"v{bus_types.PROTOCOL_VERSION}" in check["detail"]


class TestSigningKeyCheck:
    def test_warn_when_not_provisioned(self):
        check = by_id(doctor.run_doctor({}, make_context()), "signing-key")
        assert check["status"] == "warn"
        assert "not provisioned" in check["detail"]

    def test_pass_when_present(self):
        check = by_id(
            doctor.run_doctor({}, make_context(signing_key_present=lambda: True)),
            "signing-key",
        )
        assert check["status"] == "pass"

    def test_fail_when_ledger_exists_but_key_missing(self):
        check = by_id(
            doctor.run_doctor({}, make_context(signing_key_present=lambda: False)),
            "signing-key",
        )
        assert check["status"] == "fail"
        assert "keyring" in check["remediation"]


class TestLedgerCheck:
    def test_warn_when_not_initialised(self):
        check = by_id(doctor.run_doctor({}, make_context()), "ledger")
        assert check["status"] == "warn"
        assert "not initialised" in check["detail"]
        assert "FR-M10" in check["remediation"]

    def test_pass_when_chain_verifies(self):
        check = by_id(
            doctor.run_doctor(
                {}, make_context(ledger_verifier=lambda: (True, "chain verified: 12 entries"))
            ),
            "ledger",
        )
        assert check["status"] == "pass"
        assert "12 entries" in check["detail"]

    def test_fail_names_the_divergent_sequence(self):
        check = by_id(
            doctor.run_doctor(
                {},
                make_context(
                    ledger_verifier=lambda: (False, "chain broken at sequence 42")
                ),
            ),
            "ledger",
        )
        assert check["status"] == "fail"
        assert "sequence 42" in check["detail"]
        assert check["remediation"]


class TestGitHooksCheck:
    def test_warn_without_workspace(self):
        check = by_id(doctor.run_doctor({}, make_context()), "git-hooks")
        assert check["status"] == "warn"
        assert "no workspace" in check["detail"]

    def test_warn_when_not_a_git_repo(self, tmp_path):
        check = by_id(
            doctor.run_doctor({"workspaceDir": str(tmp_path)}, make_context()),
            "git-hooks",
        )
        assert check["status"] == "warn"
        assert "not a git repository" in check["detail"]

    def test_warn_when_hook_not_installed(self, tmp_path):
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        check = by_id(
            doctor.run_doctor({"workspaceDir": str(tmp_path)}, make_context()),
            "git-hooks",
        )
        assert check["status"] == "warn"
        assert "not installed" in check["detail"]
        assert "FR-M36-03" in check["remediation"]

    def test_pass_when_meridian_hook_installed(self, tmp_path):
        hooks = tmp_path / ".git" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "commit-msg").write_text(
            f"#!/bin/sh\n# appends {doctor.HOOK_MARKER} trailers\n", encoding="utf-8"
        )
        check = by_id(
            doctor.run_doctor({"workspaceDir": str(tmp_path)}, make_context()),
            "git-hooks",
        )
        assert check["status"] == "pass"

    def test_warn_on_foreign_hook(self, tmp_path):
        hooks = tmp_path / ".git" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "commit-msg").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
        check = by_id(
            doctor.run_doctor({"workspaceDir": str(tmp_path)}, make_context()),
            "git-hooks",
        )
        assert check["status"] == "warn"
        assert "not Meridian's" in check["detail"]
        assert "leaves foreign hooks untouched" in check["remediation"]

    def test_worktree_gitdir_pointer_is_followed(self, tmp_path):
        real_gitdir = tmp_path / "real" / ".git"
        (real_gitdir / "hooks").mkdir(parents=True)
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").write_text(f"gitdir: {real_gitdir}\n", encoding="utf-8")
        check = by_id(
            doctor.run_doctor({"workspaceDir": str(worktree)}, make_context()),
            "git-hooks",
        )
        # The pointer resolves to a real hooks dir with no hook installed.
        assert check["status"] == "warn"
        assert "not installed" in check["detail"]


class TestObserversCheck:
    def test_warn_when_no_observer_is_registered_in_this_process(self):
        # The observer framework shipped (F0 Workstream D). This check's warn
        # branch means "nothing is registered here" — a headless run, or a
        # sidecar that has not finished its handshake — and the text has to
        # say that. It used to read "not built yet", which told an evaluator
        # running doctor that a shipped subsystem did not exist.
        check = by_id(doctor.run_doctor({}, make_context()), "observers")
        assert check["status"] == "warn"
        assert "no observers registered" in check["detail"]
        assert "not built yet" not in check["detail"]
        assert "FR-M35-08" in check["remediation"]

    def test_pass_when_all_observers_healthy(self):
        health = lambda: [  # noqa: E731
            {"name": "claude-code", "status": "ok", "detail": "otel stream live"},
            {"name": "copilot", "status": "ok", "detail": "scm api reachable"},
        ]
        check = by_id(
            doctor.run_doctor({}, make_context(observer_health=health)), "observers"
        )
        assert check["status"] == "pass"
        assert "claude-code" in check["detail"]

    def test_warn_with_named_degradation(self):
        health = lambda: [  # noqa: E731
            {"name": "claude-code", "status": "degraded", "detail": "otel format changed"},
        ]
        check = by_id(
            doctor.run_doctor({}, make_context(observer_health=health)), "observers"
        )
        assert check["status"] == "warn"
        assert "claude-code" in check["detail"]
        # G3: degradation, never silence.
        assert "inferred" in check["remediation"]


class TestRunDoctor:
    def test_subset_selection(self):
        result = doctor.run_doctor({"checks": ["interpreter"]}, make_context())
        assert [check["id"] for check in result["checks"]] == ["interpreter"]

    def test_unknown_check_id_raises(self):
        with pytest.raises(doctor.UnknownCheckError) as excinfo:
            doctor.run_doctor({"checks": ["nope"]}, make_context())
        assert excinfo.value.unknown == ["nope"]

    def test_a_crashing_check_becomes_a_fail_entry(self, monkeypatch):
        def boom(params, context):
            raise RuntimeError("kaput")

        monkeypatch.setattr(
            doctor,
            "CHECKS",
            [doctor.CheckSpec("interpreter", "Python interpreter", boom)],
        )
        result = doctor.run_doctor({}, make_context())
        assert result["status"] == "fail"
        check = result["checks"][0]
        assert check["name"] == "Python interpreter"
        assert "kaput" in check["detail"]

    def test_aggregate_status_is_the_worst(self):
        # Default registry on this machine: interpreter/sidecar pass, the
        # not-yet-built subsystems warn — so the run warns overall.
        result = doctor.run_doctor({}, make_context())
        assert result["status"] == "warn"


class TestDoctorOverRpc:
    def setup_method(self):
        self.server = SidecarServer()

    def test_doctor_run_round_trip(self):
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "doctor/run", "params": {}}
        )
        result = response["result"]
        assert result["status"] in ("pass", "warn", "fail")
        assert [check["id"] for check in result["checks"]] == doctor.check_ids()

    def test_unknown_check_id_is_invalid_params_with_valid_ids(self):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "doctor/run",
                "params": {"checks": ["nope"]},
            }
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert response["error"]["data"]["validChecks"] == doctor.check_ids()
