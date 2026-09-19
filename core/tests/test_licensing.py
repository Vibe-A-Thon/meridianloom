"""Licensing: free Community edition, Premium by signed licence key.

The properties that matter, each with a control that shows the test can fail:

* a licence verifies only if its bytes are exactly what the licensor signed;
* only trusted keys count, and a revoked key stops counting;
* per-developer and per-machine bindings are enforced, and *only* those;
* expiry has a 14-day grace period, then premium stops (Community continues);
* the whole Flight Recorder stays free whatever the licence state;
* the development-trust escape hatch used by the test suite is inert outside a
  source checkout, so it cannot unlock a customer's installed product.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from licensing_support import DevIssuer

from meridian_core import licensing, protocol
from meridian_core.licensing import editions, keys, licence as lic, machine, store
from meridian_core.licensing.runtime import LicenceManager
from meridian_core.server import SidecarServer

NOW = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)
FP_A = "MLM1-AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"
FP_B = "MLM1-11111-22222-33333-44444-55555"
ALICE = "alice@acme.example"


@pytest.fixture(autouse=True)
def _real_licence_behaviour(monkeypatch):
    """The suite-wide fixture points MERIDIAN_LICENCE_FILE at an all-access
    development licence; these tests are about real behaviour."""
    monkeypatch.delenv(store.ENV_LICENCE_FILE, raising=False)
    monkeypatch.delenv(keys.DEV_TRUST_ENV, raising=False)


@pytest.fixture()
def issuer() -> DevIssuer:
    return DevIssuer()


def manager(issuer, tmp_path, *, fingerprint=FP_A, emails=(ALICE,), now=NOW, **kwargs) -> LicenceManager:
    return LicenceManager(
        trusted=issuer.trusted(),
        user_dir=tmp_path / "user",
        machine_dir=tmp_path / "machine",
        clock=lambda: now,
        fingerprint=lambda: fingerprint,
        developer_emails=lambda _ws: frozenset(emails),
        **kwargs,
    )


def put(tmp_path, text, name="a.mlic", scope="user"):
    directory = tmp_path / scope
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def times(**offsets_days):
    return {key: lic.format_time(NOW + timedelta(days=days)) for key, days in offsets_days.items()}


# -- signature and structure -------------------------------------------------


class TestSignature:
    def test_a_correctly_signed_licence_parses(self, issuer):
        licence = lic.parse_and_verify(issuer.issue(), issuer.trusted())
        assert licence.licensee_name == "Test Licensee Ltd"
        assert licence.grants("governor") and licence.grants("orchestra")

    def test_changing_any_signed_field_breaks_the_signature(self, issuer):
        document = json.loads(issuer.issue())
        document["payload"]["seats"] = 500  # the attractive edit
        with pytest.raises(lic.LicenceError) as caught:
            lic.parse_and_verify(json.dumps(document), issuer.trusted())
        assert caught.value.state == lic.STATE_INVALID
        assert "altered" in str(caught.value)

    def test_extending_the_expiry_by_hand_is_caught(self, issuer):
        text = issuer.issue(expiresAt=lic.format_time(NOW - timedelta(days=1)))
        document = json.loads(text)
        document["payload"]["expiresAt"] = "2099-01-01T00:00:00Z"
        with pytest.raises(lic.LicenceError):
            lic.parse_and_verify(json.dumps(document), issuer.trusted())

    def test_reformatting_the_file_does_not_matter(self, issuer):
        # The signature covers canonical JSON, not the file's whitespace.
        document = json.loads(issuer.issue())
        squashed = json.dumps(document, separators=(",", ":"))
        assert lic.parse_and_verify(squashed, issuer.trusted())

    def test_a_key_the_product_does_not_trust_is_refused(self, issuer):
        other = DevIssuer(key_id="ml-someone-else")
        with pytest.raises(lic.LicenceError) as caught:
            lic.parse_and_verify(other.issue(), issuer.trusted())
        assert caught.value.state == lic.STATE_UNTRUSTED

    def test_a_forged_key_id_does_not_borrow_anothers_trust(self, issuer):
        # Signed by an attacker's key but *claiming* the trusted key id.
        attacker = DevIssuer(key_id=issuer.key_id)
        with pytest.raises(lic.LicenceError) as caught:
            lic.parse_and_verify(attacker.issue(), issuer.trusted())
        assert caught.value.state == lic.STATE_INVALID

    def test_a_revoked_key_is_refused(self, issuer):
        with pytest.raises(lic.LicenceError) as caught:
            lic.parse_and_verify(issuer.issue(), issuer.trusted(), frozenset({issuer.key_id}))
        assert caught.value.state == lic.STATE_UNTRUSTED
        assert "revoked" in str(caught.value)

    @pytest.mark.parametrize("junk", ["", "not json", "[]", '{"format":"x"}', "\x00\x01"])
    def test_garbage_is_invalid_not_a_crash(self, issuer, junk):
        with pytest.raises(lic.LicenceError) as caught:
            lic.parse_and_verify(junk, issuer.trusted())
        assert caught.value.state == lic.STATE_INVALID

    def test_an_enormous_file_is_refused_before_parsing(self, issuer):
        with pytest.raises(lic.LicenceError, match="too large"):
            lic.parse_and_verify("x" * 70_000, issuer.trusted())

    @pytest.mark.parametrize(
        "overrides, fragment",
        [
            ({"product": "other-product"}, "different product"),
            ({"edition": "community"}, "edition"),
            ({"kind": "site"}, "kind"),
            ({"seats": 0}, "seats"),
            ({"features": ["telepathy"]}, "unknown feature"),
            ({"bindings": {"machines": ["not-a-fingerprint"]}}, "invalid machine fingerprint"),
            ({"kind": "developer", "bindings": {"developers": ["nope"]}}, "invalid developer email"),
            ({"kind": "developer", "seats": 1,
              "bindings": {"developers": ["a@x.example", "b@x.example"]}}, "only 1 seat"),
        ],
    )
    def test_vendor_side_mistakes_are_named(self, issuer, overrides, fragment):
        with pytest.raises(lic.LicenceError, match=fragment):
            lic.parse_and_verify(issuer.issue(**overrides), issuer.trusted())

    def test_a_wildcard_machine_binding_needs_a_development_key(self, issuer):
        # Control: the same licence is fine under a development key ...
        assert lic.parse_and_verify(issuer.issue(), issuer.trusted(development=True))
        # ... and refused under a production key. This is what stops anyone
        # from minting an "any machine" licence with a real key by mistake.
        with pytest.raises(lic.LicenceError, match="wildcard"):
            lic.parse_and_verify(issuer.issue(), issuer.trusted(development=False))


# -- evaluation --------------------------------------------------------------


def parsed(issuer, **overrides):
    return lic.parse_and_verify(issuer.issue(**overrides), issuer.trusted())


def evaluate(licence, *, fingerprint=FP_A, emails=(ALICE,), now=NOW):
    return lic.evaluate(licence, now=now, machine_fingerprint=fingerprint, developer_emails=frozenset(emails))


class TestEvaluation:
    def test_perpetual_licence_is_valid(self, issuer):
        status = evaluate(parsed(issuer, expiresAt=None))
        assert status.state == lic.STATE_VALID and status.days_remaining is None

    def test_dates_and_grace(self, issuer):
        base = dict(kind="machine", bindings={"machines": [FP_A]})
        valid = evaluate(parsed(issuer, **base, **times(expiresAt=30)))
        assert (valid.state, valid.days_remaining) == (lic.STATE_VALID, 30)
        grace = evaluate(parsed(issuer, **base, **times(expiresAt=-3)))
        assert grace.state == lic.STATE_GRACE and grace.premium_active
        assert "grace" in grace.reason
        expired = evaluate(parsed(issuer, **base, **times(expiresAt=-(lic.GRACE_DAYS + 1))))
        assert expired.state == lic.STATE_EXPIRED and not expired.premium_active

    def test_grace_boundary_is_exact(self, issuer):
        licence = parsed(issuer, kind="machine", bindings={"machines": [FP_A]}, **times(expiresAt=0))
        end = licence.expires_at + timedelta(days=lic.GRACE_DAYS)
        assert evaluate(licence, now=end).state == lic.STATE_GRACE
        assert evaluate(licence, now=end + timedelta(seconds=1)).state == lic.STATE_EXPIRED

    def test_not_yet_valid(self, issuer):
        status = evaluate(parsed(issuer, **times(notBefore=5)))
        assert status.state == lic.STATE_NOT_YET_VALID and not status.premium_active

    def test_machine_binding(self, issuer):
        licence = parsed(issuer, bindings={"machines": [FP_A, FP_B]}, seats=2)
        assert evaluate(licence, fingerprint=FP_B).state == lic.STATE_VALID
        wrong = evaluate(licence, fingerprint="MLM1-00000-00000-00000-00000-00000")
        assert wrong.state == lic.STATE_WRONG_MACHINE
        assert "MLM1-00000" in wrong.reason  # tells the person what to send

    def test_a_machine_with_no_identifier_cannot_use_a_machine_licence(self, issuer):
        status = evaluate(parsed(issuer, bindings={"machines": [FP_A]}), fingerprint=None)
        assert status.state == lic.STATE_WRONG_MACHINE

    def test_developer_binding_is_case_insensitive(self, issuer):
        licence = parsed(issuer, kind="developer", bindings={"developers": [ALICE.upper()]})
        assert evaluate(licence, emails=(ALICE,)).state == lic.STATE_VALID

    def test_a_different_developer_is_refused(self, issuer):
        licence = parsed(issuer, kind="developer", bindings={"developers": [ALICE]})
        status = evaluate(licence, emails=("mallory@evil.example",))
        assert status.state == lic.STATE_WRONG_DEVELOPER and not status.premium_active

    def test_no_git_identity_cannot_satisfy_a_developer_licence(self, issuer):
        licence = parsed(issuer, kind="developer", bindings={"developers": [ALICE]})
        assert evaluate(licence, emails=()).state == lic.STATE_WRONG_DEVELOPER

    def test_feature_scoped_licence(self, issuer):
        status = evaluate(parsed(issuer, features=["governor"]))
        assert status.grants("governor")
        assert not status.grants("orchestra") and not status.grants("analytics")


# -- the manager -------------------------------------------------------------


class TestManager:
    def test_no_licence_means_community(self, issuer, tmp_path):
        status = manager(issuer, tmp_path).status
        assert status.state == lic.STATE_NONE and status.edition == "community"

    def test_no_files_means_no_git_and_no_machine_lookups(self, issuer, tmp_path):
        # Community users pay nothing for a check they cannot fail.
        def boom(*_):
            raise AssertionError("should not be consulted")

        mgr = LicenceManager(
            trusted=issuer.trusted(), user_dir=tmp_path / "u", machine_dir=tmp_path / "m",
            fingerprint=boom, developer_emails=boom,
        )
        assert mgr.status.state == lic.STATE_NONE

    def test_best_licence_wins(self, issuer, tmp_path):
        put(tmp_path, issuer.issue(kind="machine", bindings={"machines": [FP_B]}), "wrong.mlic")
        put(tmp_path, issuer.issue(licenceId="ML-GOOD"), "good.mlic")
        assert manager(issuer, tmp_path).status.licence.licence_id == "ML-GOOD"

    def test_machine_directory_is_honoured(self, issuer, tmp_path):
        put(tmp_path, issuer.issue(), scope="machine")
        assert manager(issuer, tmp_path).status.premium_active

    def test_a_corrupt_file_reports_why_and_stays_community(self, issuer, tmp_path):
        put(tmp_path, "{ broken")
        status = manager(issuer, tmp_path).status
        assert status.state == lic.STATE_INVALID and not status.premium_active

    def test_the_status_reflects_time_passing(self, issuer, tmp_path):
        put(tmp_path, issuer.issue(kind="machine", bindings={"machines": [FP_A]}, **times(expiresAt=1)))
        clock = {"now": NOW}
        mgr = LicenceManager(
            trusted=issuer.trusted(), user_dir=tmp_path / "user", machine_dir=tmp_path / "machine",
            clock=lambda: clock["now"], fingerprint=lambda: FP_A,
            developer_emails=lambda _w: frozenset(),
        )
        assert mgr.reload().state == lic.STATE_VALID
        clock["now"] = NOW + timedelta(days=lic.GRACE_DAYS + 2)
        assert mgr.reload().state == lic.STATE_EXPIRED

    def test_install_stores_and_activates(self, issuer, tmp_path):
        mgr = manager(issuer, tmp_path)
        status = mgr.install(issuer.issue(licenceId="ML-INSTALLED"))
        assert status.premium_active
        assert (tmp_path / "user" / "ML-INSTALLED.mlic").is_file()

    @pytest.mark.parametrize(
        "overrides, state",
        [
            ({"bindings": {"machines": [FP_B]}}, lic.STATE_WRONG_MACHINE),
            ({"expiresAt": lic.format_time(NOW - timedelta(days=90))}, lic.STATE_EXPIRED),
            ({"notBefore": lic.format_time(NOW + timedelta(days=9))}, lic.STATE_NOT_YET_VALID),
        ],
    )
    def test_install_refuses_a_licence_that_would_not_work_here(self, issuer, tmp_path, overrides, state):
        mgr = manager(issuer, tmp_path)
        with pytest.raises(lic.LicenceError) as caught:
            mgr.install(issuer.issue(**overrides))
        assert caught.value.state == state
        assert not (tmp_path / "user").exists() or not list((tmp_path / "user").iterdir())

    def test_install_refuses_a_tampered_file_without_writing(self, issuer, tmp_path):
        document = json.loads(issuer.issue())
        document["payload"]["features"] = ["*"]
        document["payload"]["seats"] = 99
        with pytest.raises(lic.LicenceError):
            manager(issuer, tmp_path).install(json.dumps(document))
        assert not (tmp_path / "user").exists()

    def test_developer_licence_installs_when_identity_is_unknown_but_says_so(self, issuer, tmp_path):
        mgr = manager(issuer, tmp_path, emails=())
        status = mgr.install(issuer.issue(kind="developer", bindings={"developers": [ALICE]}))
        assert "user.email" in status.reason and not status.premium_active

    def test_developer_licence_for_someone_else_is_refused_when_identity_is_known(self, issuer, tmp_path):
        with pytest.raises(lic.LicenceError) as caught:
            manager(issuer, tmp_path, emails=("bob@acme.example",)).install(
                issuer.issue(kind="developer", bindings={"developers": [ALICE]})
            )
        assert caught.value.state == lic.STATE_WRONG_DEVELOPER

    def test_remove_returns_to_community(self, issuer, tmp_path):
        mgr = manager(issuer, tmp_path)
        mgr.install(issuer.issue())
        assert mgr.remove()
        assert mgr.status.state == lic.STATE_NONE

    def test_unknown_scope_is_an_error(self, issuer, tmp_path):
        with pytest.raises(ValueError, match="scope"):
            manager(issuer, tmp_path).install(issuer.issue(), scope="galaxy")


# -- enforcement -------------------------------------------------------------


PREMIUM_SAMPLES = {
    "gate.approve": "governor",
    "run/start": "governor",
    "worktree/create": "governor",
    "portability/export": "governor",
    "loop.start": "orchestra",
    "router/requestModelCall": "orchestra",
    "adapters/plug": "orchestra",
    "trust/doraExport": "analytics",
    "spend/forecast": "analytics",
    "evidence/gate": "analytics",
}
COMMUNITY_SAMPLES = [
    "handshake", "ping", "health", "shutdown", "licence/status", "licence/install", "licence/remove",
    "ledger.append", "ledger.query", "ledger.verify", "ledger.exportBundle", "attrib/blame",
    "observe/sessions", "hook/install", "interop/export", "trust/rejectionRate", "trust/score",
    "spend/series", "spend/pricing", "simulation/serve", "doctor/run",
]


class TestEnforcement:
    @pytest.mark.parametrize("method, feature", sorted(PREMIUM_SAMPLES.items()))
    def test_premium_methods_need_a_licence(self, issuer, tmp_path, method, feature):
        denial = manager(issuer, tmp_path).check_method(method)
        assert denial is not None
        assert denial["data"]["feature"] == feature
        assert denial["data"]["edition"] == "community"
        assert "Install" in denial["data"]["remediation"]

    @pytest.mark.parametrize("method, feature", sorted(PREMIUM_SAMPLES.items()))
    def test_a_full_licence_unlocks_them(self, issuer, tmp_path, method, feature):
        mgr = manager(issuer, tmp_path)
        mgr.install(issuer.issue())
        assert mgr.check_method(method) is None

    @pytest.mark.parametrize("method", COMMUNITY_SAMPLES)
    def test_the_free_edition_is_never_gated(self, issuer, tmp_path, method):
        assert manager(issuer, tmp_path).check_method(method) is None

    @pytest.mark.parametrize("state_setup", ["expired", "wrong-machine", "corrupt"])
    def test_a_bad_licence_leaves_the_free_edition_working(self, issuer, tmp_path, state_setup):
        text = {
            "expired": issuer.issue(expiresAt=lic.format_time(NOW - timedelta(days=200))),
            "wrong-machine": issuer.issue(bindings={"machines": [FP_B]}),
            "corrupt": "nonsense",
        }[state_setup]
        put(tmp_path, text)
        mgr = manager(issuer, tmp_path)
        assert mgr.check_method("gate.approve") is not None
        for method in COMMUNITY_SAMPLES:
            assert mgr.check_method(method) is None

    def test_feature_scoped_licence_unlocks_only_its_features(self, issuer, tmp_path):
        mgr = manager(issuer, tmp_path)
        mgr.install(issuer.issue(features=["governor"]))
        assert mgr.check_method("gate.approve") is None
        denied = mgr.check_method("loop.start")
        assert denied and "does not include" in denied["message"]
        assert mgr.check_method("trust/doraExport") is not None

    def test_grace_period_still_unlocks(self, issuer, tmp_path):
        put(tmp_path, issuer.issue(bindings={"machines": [FP_A]}, **times(expiresAt=-2)))
        assert manager(issuer, tmp_path).check_method("gate.approve") is None


class TestEditionsRegistry:
    def test_every_capability_has_an_explicit_edition_decision(self):
        rows = editions.feature_table()
        assert len(rows) >= 30
        tiers_seen = {row["tier"] for row in rows}
        unknown = tiers_seen - {"flight-recorder"} - set(editions.PREMIUM_TIERS)
        assert not unknown, f"tier(s) {unknown} have no edition decision in licensing/editions.py"

    def test_overrides_name_real_methods(self):
        import bus_types

        known = {m for cap in bus_types.CAPABILITIES for m in cap["rpcMethods"]}
        assert set(editions.PREMIUM_METHOD_OVERRIDES) <= known

    def test_override_features_are_licensable(self):
        allowed = set(lic.FEATURES)
        assert set(editions.PREMIUM_METHOD_OVERRIDES.values()) <= allowed
        assert set(editions.PREMIUM_TIERS.values()) <= allowed

    def test_the_whole_flight_recorder_stays_free_except_named_analytics(self):
        import bus_types

        for capability in bus_types.CAPABILITIES:
            if capability["tier"] != "flight-recorder":
                continue
            for method in capability["rpcMethods"]:
                feature = editions.required_feature(method)
                assert feature in (None, "analytics"), method
                if feature:
                    assert method in editions.PREMIUM_METHOD_OVERRIDES

    def test_licence_management_is_always_available(self):
        for method in ("licence/status", "licence/install", "licence/remove"):
            assert editions.required_feature(method) is None


# -- machine fingerprint -----------------------------------------------------


class TestFingerprint:
    def test_format_and_determinism(self):
        first = machine.fingerprint_for("ABC-123")
        assert first == machine.fingerprint_for("abc-123 ")  # case/space-insensitive
        assert lic._FINGERPRINT.match(first)
        assert first != machine.fingerprint_for("ABC-124")

    def test_it_is_one_way(self):
        assert "ABC-123" not in machine.fingerprint_for("ABC-123")

    def test_this_machine_has_a_fingerprint_or_says_so(self):
        value = machine.machine_fingerprint()
        assert value is None or lic._FINGERPRINT.match(value)


# -- the development-trust hatch is inert in an installed product ------------


class TestDevelopmentTrust:
    def test_honoured_in_a_source_checkout(self, issuer, tmp_path, monkeypatch):
        trust = tmp_path / "dev.key"
        trust.write_text(issuer.public_b64 + "\n", encoding="ascii")
        monkeypatch.setenv(keys.DEV_TRUST_ENV, str(trust))
        monkeypatch.setattr(keys, "is_source_checkout", lambda: True)
        assert keys.DEV_KEY_ID in keys.trusted_keys()

    def test_ignored_outside_a_source_checkout(self, issuer, tmp_path, monkeypatch):
        # Negative control: identical setup, but as an installed product.
        trust = tmp_path / "dev.key"
        trust.write_text(issuer.public_b64 + "\n", encoding="ascii")
        monkeypatch.setenv(keys.DEV_TRUST_ENV, str(trust))
        monkeypatch.setattr(keys, "is_source_checkout", lambda: False)
        assert keys.DEV_KEY_ID not in keys.trusted_keys()

    def test_this_checkout_is_detected_as_one(self):
        assert keys.is_source_checkout()

    def test_a_dev_licence_does_not_unlock_a_packaged_product(self, issuer, tmp_path, monkeypatch):
        trust = tmp_path / "dev.key"
        trust.write_text(issuer.public_b64 + "\n", encoding="ascii")
        (tmp_path / "user").mkdir()
        (tmp_path / "user" / "dev.mlic").write_text(issuer.issue(), encoding="utf-8")
        monkeypatch.setenv(keys.DEV_TRUST_ENV, str(trust))
        monkeypatch.setattr(keys, "is_source_checkout", lambda: False)
        mgr = LicenceManager(user_dir=tmp_path / "user", machine_dir=tmp_path / "machine")
        assert not mgr.status.premium_active
        assert mgr.check_method("gate.approve") is not None

    def test_the_shipped_public_keys_are_well_formed(self):
        assert keys.PRODUCTION_KEYS, "no production licence key is configured"
        for key_id, encoded in keys.PRODUCTION_KEYS.items():
            assert keys._decode(encoded) is not None, f"{key_id} is not a 32-byte base64 Ed25519 key"
        assert set(keys.trusted_keys()) >= set(keys.PRODUCTION_KEYS)


# -- through the sidecar -----------------------------------------------------


def rpc(server, method, params=None, rid=7):
    return server.handle_message({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})


def open_server(issuer, tmp_path, **kwargs):
    server = SidecarServer(licence=manager(issuer, tmp_path, **kwargs))
    server.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "handshake",
        "params": {"protocolVersion": protocol.PROTOCOL_VERSION, "client": "pytest",
                   "tiers": ["flight-recorder", "governor", "orchestra"]},
    })
    return server


class TestThroughTheSidecar:
    def test_community_refuses_premium_with_an_actionable_error(self, issuer, tmp_path):
        response = rpc(open_server(issuer, tmp_path), "gate.status", {"subject": "main"})
        error = response["error"]
        assert error["code"] == protocol.ERROR_LICENCE_REQUIRED == -32006
        assert error["data"]["feature"] == "governor"
        assert error["data"]["licenceState"] == "none"
        assert "Install" in error["data"]["remediation"]

    def test_the_licence_gate_runs_after_the_tier_gate(self, issuer, tmp_path):
        server = SidecarServer(licence=manager(issuer, tmp_path))  # governor tier NOT enabled
        response = rpc(server, "gate.status", {"subject": "main"})
        assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED

    def test_free_methods_work_without_any_licence(self, issuer, tmp_path):
        server = open_server(issuer, tmp_path)
        assert rpc(server, "ping")["result"]["pong"] is True
        assert rpc(server, "health")["result"]["status"] == "ok"

    def test_status_reports_community_then_premium_after_install(self, issuer, tmp_path):
        server = open_server(issuer, tmp_path)
        assert rpc(server, "licence/status")["result"]["edition"] == "community"
        installed = rpc(server, "licence/install", {"text": issuer.issue()})["result"]
        assert installed["edition"] == "premium" and installed["premiumActive"] is True
        assert installed["licence"]["licensee"] == "Test Licensee Ltd"
        assert "signature" not in json.dumps(installed)
        after = rpc(server, "gate.status", {"subject": "main"})
        assert after.get("error", {}).get("code") != protocol.ERROR_LICENCE_REQUIRED

    def test_install_from_a_path(self, issuer, tmp_path):
        server = open_server(issuer, tmp_path)
        source = tmp_path / "from-vendor.mlic"
        source.write_text(issuer.issue(), encoding="utf-8")
        assert rpc(server, "licence/install", {"path": str(source)})["result"]["premiumActive"]

    def test_a_bad_licence_is_refused_and_leaves_no_trace(self, issuer, tmp_path):
        server = open_server(issuer, tmp_path)
        document = json.loads(issuer.issue())
        document["payload"]["seats"] = 1000
        response = rpc(server, "licence/install", {"text": json.dumps(document)})
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert response["error"]["data"]["state"] == "invalid"
        assert rpc(server, "licence/status")["result"]["edition"] == "community"
        assert not (tmp_path / "user").exists()

    def test_install_needs_exactly_one_source(self, issuer, tmp_path):
        server = open_server(issuer, tmp_path)
        assert rpc(server, "licence/install", {})["error"]["code"] == protocol.INVALID_PARAMS
        both = rpc(server, "licence/install", {"text": "x", "path": "y"})
        assert both["error"]["code"] == protocol.INVALID_PARAMS

    def test_remove_returns_to_community_and_locks_premium_again(self, issuer, tmp_path):
        server = open_server(issuer, tmp_path)
        rpc(server, "licence/install", {"text": issuer.issue()})
        removed = rpc(server, "licence/remove", {})["result"]
        assert removed["removed"] and removed["status"]["edition"] == "community"
        assert rpc(server, "gate.status", {"subject": "main"})["error"]["code"] == protocol.ERROR_LICENCE_REQUIRED

    def test_status_can_include_this_machines_fingerprint(self, issuer, tmp_path):
        server = open_server(issuer, tmp_path)
        result = rpc(server, "licence/status", {"includeFingerprint": True})["result"]
        assert "machineFingerprint" in result

    def test_an_expired_licence_can_always_be_replaced(self, issuer, tmp_path):
        put(tmp_path, issuer.issue(bindings={"machines": [FP_A]}, **times(expiresAt=-200)))
        server = open_server(issuer, tmp_path)
        assert rpc(server, "licence/status")["result"]["state"] == "expired"
        renewed = rpc(server, "licence/install", {"text": issuer.issue(licenceId="ML-RENEWED")})
        assert renewed["result"]["premiumActive"]


# -- the licensor's tool -----------------------------------------------------


def _load_tool():
    path = Path(__file__).resolve().parents[2] / "tools" / "licensing" / "meridian_licence.py"
    spec = importlib.util.spec_from_file_location("meridian_licence_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestIssuerTool:
    def test_keygen_issue_then_the_product_accepts_it(self, tmp_path, monkeypatch, capsys):
        tool = _load_tool()
        assert tool.main(["keygen", "--out-dir", str(tmp_path), "--key-id", "ml-test-1"]) == 0
        public = (tmp_path / "ml-test-1.public.key").read_text().strip()
        monkeypatch.setattr(keys, "PRODUCTION_KEYS", {"ml-test-1": public})
        out = tmp_path / "customer.mlic"
        assert tool.main([
            "issue", "--key", str(tmp_path / "ml-test-1.private.key"), "--key-id", "ml-test-1",
            "--licensee", "Acme Software Ltd", "--contact", "it@acme.example",
            "--kind", "developer", "--developer", ALICE, "--days", "365", "--out", str(out),
        ]) == 0
        mgr = LicenceManager(
            user_dir=tmp_path / "user", machine_dir=tmp_path / "machine",
            developer_emails=lambda _w: frozenset({ALICE}),
        )
        status = mgr.install(out.read_text())
        assert status.premium_active and status.licence.licensee_name == "Acme Software Ltd"
        assert status.licence.kind == "developer" and status.licence.seats == 1

    def test_keygen_refuses_to_overwrite_a_private_key(self, tmp_path):
        tool = _load_tool()
        assert tool.main(["keygen", "--out-dir", str(tmp_path), "--key-id", "k"]) == 0
        with pytest.raises(SystemExit, match="refusing to overwrite"):
            tool.main(["keygen", "--out-dir", str(tmp_path), "--key-id", "k"])

    def test_a_licence_signed_by_an_unlisted_key_is_rejected_by_the_product(self, tmp_path):
        tool = _load_tool()
        tool.main(["keygen", "--out-dir", str(tmp_path), "--key-id", "ml-rogue-1"])
        out = tmp_path / "rogue.mlic"
        tool.main([
            "issue", "--key", str(tmp_path / "ml-rogue-1.private.key"), "--key-id", "ml-rogue-1",
            "--licensee", "Rogue", "--kind", "developer", "--developer", ALICE, "--out", str(out),
        ])
        # Not added to PRODUCTION_KEYS -> the shipped product does not trust it.
        with pytest.raises(lic.LicenceError) as caught:
            lic.parse_and_verify(out.read_bytes(), {k: lic.TrustedKey(k, b"\0" * 32)
                                                    for k in keys.PRODUCTION_KEYS})
        assert caught.value.state == lic.STATE_UNTRUSTED

    def test_the_private_key_is_not_in_the_repository(self):
        import subprocess

        from meridian_core.childenv import child_environment

        root = Path(__file__).resolve().parents[2]
        tracked = subprocess.run(
            ["git", "ls-files", "*.private.key", "*.private.pem"],
            cwd=root, capture_output=True, text=True, env=child_environment(), check=False,
        ).stdout.split()
        assert tracked == []
        ignore = (root / ".gitignore").read_text(encoding="utf-8")
        assert "*.private.key" in ignore
