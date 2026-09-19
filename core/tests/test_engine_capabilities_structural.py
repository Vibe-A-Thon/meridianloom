"""Structural capability set (FR-M33-02 slice 2a; FR-M28-02/-05/-07).

The four structural capabilities registered into the slice-1
``CapabilityRegistry`` seam and routed end-to-end by dispatch (FR-M33-03):

* ``structural_parse``   — tree-sitter structural edits with re-parse
                           validation (extends the F0 attribution usage);
* ``symbol_resolution``  — LSP bridge over a REAL subprocess speaking
                           JSON-RPC Content-Length framing (the fixture
                           server), degrading honestly when no server
                           exists, cannot spawn or times out;
* ``diff_patch``         — unified diff production and deterministic patch
                           application with named rejections;
* ``hunk_edit``          — hunk-scoped large-file editing (FR-M28-05) with
                           generated/binary exclusion (FR-M28-07).

Zero model calls throughout (FR-M36-07) — the engine tests assert the
package scan separately (tests/test_no_model_calls.py).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from meridian_core.engine.capabilities import CapabilityRegistry
from meridian_core.engine.catalogue import load_catalogue, repo_default_paths
from meridian_core.engine.diffing import DiffPatchCapability
from meridian_core.engine.dispatch import Dispatcher
from meridian_core.engine.hunks import GENERATED_PATTERNS, HunkEditCapability
from meridian_core.engine.lsp_bridge import SymbolResolutionCapability
from meridian_core.engine.structural import StructuralParseCapability

FIXTURES = Path(__file__).resolve().parent / "fixtures"
JAVA_FIXTURE = FIXTURES / "structural" / "Sample.java"
PYTHON_FIXTURE = FIXTURES / "structural" / "sample.py"
FAKE_LSP = FIXTURES / "lsp" / "fake_lsp_server.py"


@pytest.fixture()
def structural():
    return StructuralParseCapability()


@pytest.fixture()
def resolver():
    return SymbolResolutionCapability()


@pytest.fixture()
def differ():
    return DiffPatchCapability()


@pytest.fixture()
def hunker():
    return HunkEditCapability()


def lsp_config(timeout: float = 10.0) -> dict:
    """The server command comes from CONFIG (as policy/workspace config
    would supply it) — never hard-coded in the bridge."""
    return {
        "servers": {"python": {"command": [sys.executable, str(FAKE_LSP)]}},
        "timeout_seconds": timeout,
    }


class TestStructuralParse:
    """FR-M33-02 structural edits (tree-sitter, FR-M28-02)."""

    def test_parse_op_lists_java_definitions(self, structural):
        outcome = structural.run({"op": "parse", "path": str(JAVA_FIXTURE)})
        assert outcome.handled is True
        result = outcome.result
        assert result["language"] == "java"
        assert result["has_error"] is False
        names = {(d["type"], d["name"]) for d in result["definitions"]}
        assert ("class_declaration", "PaymentController") in names
        assert ("method_declaration", "submit") in names
        spans = {d["name"]: (d["start_line"], d["end_line"]) for d in result["definitions"]}
        assert spans["submit"][0] < spans["submit"][1]

    def test_parse_op_python(self, structural):
        outcome = structural.run({"op": "parse", "path": str(PYTHON_FIXTURE)})
        assert outcome.handled is True
        names = {d["name"] for d in outcome.result["definitions"]}
        assert {"Ledger", "total", "main"} <= names

    def test_unknown_language_reports_unavailable(self, structural, tmp_path):
        """Degradation: no grammar → no_deterministic_path, never a crash
        or a fabricated tree."""
        target = tmp_path / "notes.txt"
        target.write_text("hello\n", encoding="utf-8")
        outcome = structural.run({"op": "parse", "path": str(target)})
        assert outcome.handled is False
        assert ".txt" in outcome.reason and "unavailable" in outcome.reason

    def test_replace_method_reparse_clean(self, structural):
        """A structural edit replaces a named node region and returns the
        edited source; the edit is applied only if the re-parse is clean."""
        new_method = (
            "    public Receipt submit(Order order) {\n"
            "        Receipt receipt = charge(order);\n"
            "        ledger.record(receipt);\n"
            "        return receipt;\n"
            "    }\n"
        )
        outcome = structural.run(
            {
                "op": "edit",
                "path": str(JAVA_FIXTURE),
                "target": {"node_type": "method_declaration", "name": "submit"},
                "edit": {"kind": "replace", "text": new_method},
            }
        )
        assert outcome.handled is True
        assert "ledger.record(receipt);" in outcome.result["text"]
        # Pure function: the fixture file on disk is untouched.
        assert "ledger.record" not in JAVA_FIXTURE.read_text(encoding="utf-8")

    def test_delete_method_reparse_clean(self, structural):
        outcome = structural.run(
            {
                "op": "edit",
                "path": str(JAVA_FIXTURE),
                "target": {"node_type": "method_declaration", "name": "emptyReceipt"},
                "edit": {"kind": "delete"},
            }
        )
        assert outcome.handled is True
        assert "emptyReceipt" not in outcome.result["text"]
        assert "class Defaults" in outcome.result["text"]

    def test_insert_method_into_python_class(self, structural):
        outcome = structural.run(
            {
                "op": "edit",
                "path": str(PYTHON_FIXTURE),
                "target": {"node_type": "class_definition", "name": "Ledger"},
                "edit": {
                    "kind": "insert",
                    "text": "\n    def count(self):\n        return len(self.entries)\n",
                },
            }
        )
        assert outcome.handled is True
        text = outcome.result["text"]
        assert "def count(self):" in text

    def test_broken_edit_refused_and_named(self, structural):
        """Syntax-aware validation: an edit that breaks the parse is
        refused with the failure named; nothing is produced."""
        outcome = structural.run(
            {
                "op": "edit",
                "path": str(JAVA_FIXTURE),
                "target": {"node_type": "method_declaration", "name": "submit"},
                "edit": {"kind": "replace", "text": "public Receipt submit(Order order) {\n"},
            }
        )
        assert outcome.handled is False
        assert "edit refused" in outcome.reason
        assert "re-parse" in outcome.reason

    def test_missing_target_refused_and_named(self, structural):
        outcome = structural.run(
            {
                "op": "edit",
                "path": str(JAVA_FIXTURE),
                "target": {"node_type": "method_declaration", "name": "nope"},
                "edit": {"kind": "delete"},
            }
        )
        assert outcome.handled is False
        assert "'nope'" in outcome.reason

    def test_malformed_payload_never_raises(self, structural):
        for payload in ({}, {"op": "edit"}, {"op": "edit", "path": str(JAVA_FIXTURE)}):
            outcome = structural.run(payload)
            assert outcome.handled is False


class TestSymbolResolution:
    """FR-M33-02 LSP symbol resolution/references (FR-M28-01)."""

    def test_definition_via_real_subprocess(self, resolver, tmp_path):
        outcome = resolver.run(
            {
                "workspace": str(tmp_path),
                "language": "python",
                "query": "definition",
                "path": str(tmp_path / "app.py"),
                "line": 12,
                "character": 8,
                "config": lsp_config(),
            }
        )
        assert outcome.handled is True
        (location,) = outcome.result["locations"]
        assert location["range"]["start"] == {"line": 11, "character": 4}
        assert location["uri"].endswith("app.py")

    def test_references_via_real_subprocess(self, resolver, tmp_path):
        outcome = resolver.run(
            {
                "workspace": str(tmp_path),
                "language": "python",
                "query": "references",
                "path": str(tmp_path / "app.py"),
                "line": 5,
                "character": 0,
                "config": lsp_config(),
            }
        )
        assert outcome.handled is True
        assert len(outcome.result["locations"]) == 2

    def test_workspace_symbols_via_real_subprocess(self, resolver, tmp_path):
        outcome = resolver.run(
            {
                "workspace": str(tmp_path),
                "language": "python",
                "query": "symbols",
                "symbol_query": "Ledger",
                "config": lsp_config(),
            }
        )
        assert outcome.handled is True
        (symbol,) = outcome.result["locations"]
        assert symbol["name"] == "Ledger"

    def test_unconfigured_language_reports_unavailable(self, resolver, tmp_path):
        """Honest degradation: no server configured → unavailable, and NO
        fabricated result — result stays None."""
        outcome = resolver.run(
            {
                "workspace": str(tmp_path),
                "language": "rust",
                "query": "definition",
                "path": str(tmp_path / "lib.rs"),
                "line": 0,
                "character": 0,
                "config": {"servers": {}},
            }
        )
        assert outcome.handled is False
        assert outcome.result is None
        assert "rust" in outcome.reason and "unavailable" in outcome.reason

    def test_missing_server_binary_degrades_honestly(self, resolver, tmp_path):
        outcome = resolver.run(
            {
                "workspace": str(tmp_path),
                "language": "python",
                "query": "definition",
                "path": str(tmp_path / "app.py"),
                "line": 0,
                "character": 0,
                "config": {
                    "servers": {"python": {"command": ["no-such-langserver-xyz"]}},
                    "timeout_seconds": 5,
                },
            }
        )
        assert outcome.handled is False
        assert outcome.result is None
        assert "no-such-langserver-xyz" in outcome.reason

    def test_timeout_reports_no_deterministic_path(self, resolver, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_LSP_DELAY_SECONDS", "3")
        outcome = resolver.run(
            {
                "workspace": str(tmp_path),
                "language": "python",
                "query": "definition",
                "path": str(tmp_path / "app.py"),
                "line": 0,
                "character": 0,
                "config": lsp_config(timeout=0.3),
            }
        )
        assert outcome.handled is False
        assert outcome.result is None
        assert "timed out" in outcome.reason


class TestDiffPatch:
    """FR-M33-02 unified diff + deterministic patch application."""

    OLD = "one\ntwo\nthree\n"
    NEW = "one\nTWO\nthree\nfour\n"

    def test_unified_diff_production_is_deterministic(self, differ):
        outcome = differ.run(
            {"op": "diff", "old_text": self.OLD, "new_text": self.NEW, "from_label": "x.txt", "to_label": "y.txt"}
        )
        assert outcome.handled is True
        assert outcome.result["diff"] == (
            "--- a/x.txt\n"
            "+++ b/y.txt\n"
            "@@ -1,3 +1,4 @@\n"
            " one\n"
            "-two\n"
            "+TWO\n"
            " three\n"
            "+four\n"
        )
        # Replay-identical (FR-M33-08): same inputs → same bytes; default
        # labels are a/ b/ and the hunk body is byte-identical.
        again = differ.run({"op": "diff", "old_text": self.OLD, "new_text": self.NEW})
        assert again.result["diff"] == outcome.result["diff"].replace(
            "--- a/x.txt\n+++ b/y.txt\n", "--- a/a\n+++ b/b\n"
        )

    def test_patch_apply_round_trip(self, differ):
        diff = differ.run({"op": "diff", "old_text": self.OLD, "new_text": self.NEW}).result["diff"]
        outcome = differ.run({"op": "apply", "old_text": self.OLD, "patch": diff})
        assert outcome.handled is True
        assert outcome.result["text"] == self.NEW
        assert outcome.result["rejected"] == []
        assert outcome.result["complete"] is True

    def test_hunk_mismatch_is_a_named_rejection_never_silent(self, differ):
        """A hunk whose context does not match is reported by name — never
        dropped, never half-applied without saying so."""
        patch = (
            "--- a/f\n"
            "+++ b/f\n"
            "@@ -1,2 +1,2 @@\n"
            " nothing-like-the-file\n"
            "-two\n"
            "+TWO\n"
        )
        outcome = differ.run({"op": "apply", "old_text": self.OLD, "patch": patch})
        assert outcome.handled is True
        result = outcome.result
        assert result["complete"] is False
        assert len(result["rejected"]) == 1
        assert result["rejected"][0]["hunk"].startswith("@@ -1,2 +1,2 @@")
        assert result["rejected"][0]["reason"]
        assert result["text"] == self.OLD  # nothing applied

    def test_partial_apply_reports_both_lists(self, differ):
        """Two hunks, one matching and one not: the applied hunk lands, the
        rejected one is named, both are reported."""
        old = "alpha\nbeta\ngamma\ndelta\nepsilon\nzeta\n"
        new = "alpha\nBETA\ngamma\ndelta\nepsilon\nZETA\n"
        patch = (
            "--- a/f\n"
            "+++ b/f\n"
            "@@ -1,3 +1,3 @@\n"
            " alpha\n"
            "-beta\n"
            "+BETA\n"
            " gamma\n"
            "@@ -4,2 +4,2 @@\n"
            " does-not-match\n"
            "-epsilon\n"
            "+ZETA\n"
        )
        outcome = differ.run({"op": "apply", "old_text": old, "patch": patch})
        assert outcome.handled is True
        result = outcome.result
        assert result["text"] == "alpha\nBETA\ngamma\ndelta\nepsilon\nzeta\n"
        assert result["applied"] == ["@@ -1,3 +1,3 @@"]
        assert [r["hunk"] for r in result["rejected"]] == ["@@ -4,2 +4,2 @@"]

    def test_offset_tracking_after_applied_hunk(self, differ):
        """A later hunk's header positions refer to the ORIGINAL text; the
        running offset from earlier applied hunks relocates it."""
        old = "a\nb\nc\nd\ne\nf\n"
        # Insert one line after line 1, then change line 6 (originally f).
        patch = (
            "--- a/f\n+++ b/f\n"
            "@@ -1,1 +1,2 @@\n a\n+inserted\n"
            "@@ -6,1 +7,1 @@\n-f\n+F\n"
        )
        outcome = differ.run({"op": "apply", "old_text": old, "patch": patch})
        assert outcome.handled is True
        assert outcome.result["text"] == "a\ninserted\nb\nc\nd\ne\nF\n"
        assert outcome.result["rejected"] == []

    def test_malformed_patch_refused_and_named(self, differ):
        outcome = differ.run({"op": "apply", "old_text": self.OLD, "patch": "garbage\n"})
        assert outcome.handled is False
        assert "invalid patch" in outcome.reason


class TestHunkEdit:
    """FR-M28-05 hunk-only large-file editing; FR-M28-07 generated/binary
    exclusion."""

    def test_hunk_scoped_edit_applies(self, hunker, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("def one():\n    return 1\n\ndef two():\n    return 2\n", encoding="utf-8", newline="")
        outcome = hunker.run(
            {
                "path": str(target),
                "hunks": [
                    {
                        "context": ["def two():\n"],
                        "old": ["    return 2\n"],
                        "new": ["    return 22\n"],
                    }
                ],
            }
        )
        assert outcome.handled is True
        assert target.read_text(encoding="utf-8").endswith("def two():\n    return 22\n")
        assert outcome.result["hunks_applied"][0]["matched_line"] == 4

    def test_large_file_streams_only_the_hunk_window(self, hunker, tmp_path):
        """FR-M28-05: a big file is never loaded whole — the peak in-memory
        window equals the hunk's block size, far below the file length."""
        target = tmp_path / "big.log"
        target.write_text("".join(f"line {n}\n" for n in range(1, 5001)), encoding="utf-8", newline="")
        outcome = hunker.run(
            {
                "path": str(target),
                "hunks": [
                    {
                        "context": ["line 2500\n"],
                        "old": ["line 2501\n"],
                        "new": ["line twenty-five-o-one\n"],
                    }
                ],
            }
        )
        assert outcome.handled is True
        lines = target.read_text(encoding="utf-8").splitlines()
        assert lines[2500] == "line twenty-five-o-one"
        assert lines[2499] == "line 2500"  # context preserved
        assert lines[2501] == "line 2502"  # after-block untouched
        assert outcome.result["window_lines"] <= 2
        assert outcome.result["window_lines"] < 5000

    def test_mismatch_refuses_atomically_and_names_the_hunk(self, hunker, tmp_path):
        target = tmp_path / "app.py"
        original = "alpha\nbeta\ngamma\n"
        target.write_text(original, encoding="utf-8", newline="")
        outcome = hunker.run(
            {
                "path": str(target),
                "hunks": [
                    {"context": ["not-in-the-file\n"], "old": ["beta\n"], "new": ["BETA\n"]}
                ],
            }
        )
        assert outcome.handled is False
        assert "hunks[0]" in outcome.reason
        assert target.read_text(encoding="utf-8") == original  # file untouched

    @pytest.mark.parametrize(
        "name",
        [
            "package-lock.json",
            "yarn.lock",
            "Cargo.lock",
            "poetry.lock",
            "payments.pb.go",
            "ledger_pb2.py",
            "schema.graphql.ts",
            "app.min.js",
            "app.min.css",
        ],
    )
    def test_generated_files_refused_with_path_named(self, hunker, tmp_path, name):
        """FR-M28-07: every category of generated file is refused before any
        edit, and the refusal names the path."""
        target = tmp_path / name
        target.write_text("generated contents\n", encoding="utf-8", newline="")
        outcome = hunker.run(
            {
                "path": str(target),
                "hunks": [{"context": [], "old": ["generated contents\n"], "new": ["x\n"]}],
            }
        )
        assert outcome.handled is False
        assert "FR-M28-07" in outcome.reason
        assert str(target) in outcome.reason

    def test_payload_can_extend_exclusions_not_shrink(self, hunker, tmp_path):
        target = tmp_path / "custom.codegen.py"
        target.write_text("# generated by our codegen\n", encoding="utf-8", newline="")
        base = hunker.run(
            {
                "path": str(target),
                "hunks": [{"context": [], "old": ["# generated by our codegen\n"], "new": ["x\n"]}],
            }
        )
        assert base.handled is True  # not in the default list → editable
        extended = hunker.run(
            {
                "path": str(target),
                "hunks": [{"context": [], "old": ["# generated by our codegen\n"], "new": ["x\n"]}],
                "generated_patterns": ["*.codegen.py"],
            }
        )
        assert extended.handled is False
        assert "FR-M28-07" in extended.reason

    def test_binary_file_refused(self, hunker, tmp_path):
        target = tmp_path / "blob.dat"
        target.write_bytes(b"\x00\x01\x02\x03")
        outcome = hunker.run(
            {
                "path": str(target),
                "hunks": [{"context": [], "old": ["x\n"], "new": ["y\n"]}],
            }
        )
        assert outcome.handled is False
        assert "binary" in outcome.reason

    def test_default_patterns_are_conservative(self):
        """The exclusion list is data: lockfiles, protobuf/graphql outputs,
        minified bundles — and nothing broader like '*.py' or '*.json'."""
        joined = " ".join(GENERATED_PATTERNS)
        assert "lock" in joined and "*.pb.go" in joined and "*.min.js" in joined
        assert not any(p in ("*.py", "*.json", "*.js", "*") for p in GENERATED_PATTERNS)


class TestDispatchEndToEnd:
    """FR-M33-03: dispatch routes the structural capabilities end-to-end
    against the real D16 catalogue (policy/action-classes.yaml)."""

    @pytest.fixture()
    def dispatcher(self):
        catalogue = load_catalogue(repo_default_paths())
        registry = CapabilityRegistry(catalogue)
        from meridian_core.engine import structural_capability_set

        # Each capability binds to the class the catalogue assigns it.
        for capability in structural_capability_set():
            for class_id, entry in catalogue.classes.items():
                if entry.capability == capability.name:
                    assert registry.register(class_id, capability), capability.name
        assert registry.refusals == []
        return Dispatcher(catalogue=catalogue, registry=registry)

    def test_capabilities_register_clean_against_repo_catalogue(self, dispatcher):
        for class_id, capability_name in (
            ("parse", "structural_parse"),
            ("resolve_symbol", "symbol_resolution"),
            ("apply_patch", "diff_patch"),
            ("hunk_edit", "hunk_edit"),
        ):
            entry = dispatcher.catalogue.lookup(class_id)
            assert entry is not None and entry.capability == capability_name

    def test_dispatch_parse_executes_deterministically(self, dispatcher):
        outcome = dispatcher.dispatch(
            "parse",
            {
                "op": "edit",
                "path": str(PYTHON_FIXTURE),
                "target": {"node_type": "function_definition", "name": "main"},
                "edit": {"kind": "insert", "text": "\n\n# appended\n"},
            },
        )
        assert outcome.kind == "executed"
        assert outcome.router_eligible is False
        assert outcome.capability == "structural_parse"
        assert "# appended" in outcome.result["text"]

    def test_dispatch_resolve_symbol_executes_via_configured_server(self, dispatcher, tmp_path):
        outcome = dispatcher.dispatch(
            "resolve_symbol",
            {
                "workspace": str(tmp_path),
                "language": "python",
                "query": "definition",
                "path": str(tmp_path / "a.py"),
                "line": 3,
                "character": 2,
                "config": lsp_config(),
            },
        )
        assert outcome.kind == "executed"
        assert outcome.router_eligible is False
        assert len(outcome.result["locations"]) == 1

    def test_dispatch_resolve_symbol_refuses_when_unconfigured(self, dispatcher, tmp_path):
        """No server in config: the action is REFUSED (parse/resolve_symbol
        carry no escalateIf), never routed to a model."""
        outcome = dispatcher.dispatch(
            "resolve_symbol",
            {
                "workspace": str(tmp_path),
                "language": "go",
                "query": "definition",
                "path": str(tmp_path / "a.go"),
                "line": 0,
                "character": 0,
                "config": {"servers": {}},
            },
        )
        assert outcome.kind == "refused"
        assert outcome.router_eligible is False
        assert "unavailable" in outcome.reason

    def test_dispatch_apply_patch_executes(self, dispatcher):
        outcome = dispatcher.dispatch(
            "apply_patch",
            {"op": "diff", "old_text": "a\nb\n", "new_text": "a\nB\n", "from_label": "f"},
        )
        assert outcome.kind == "executed"
        assert outcome.router_eligible is False
        assert "-b\n+B\n" in outcome.result["diff"]

    def test_dispatch_hunk_edit_executes(self, dispatcher, tmp_path):
        target = tmp_path / "notes.txt"
        target.write_text("first\nsecond\nthird\n", encoding="utf-8", newline="")
        outcome = dispatcher.dispatch(
            "hunk_edit",
            {
                "path": str(target),
                "hunks": [{"context": ["second\n"], "old": ["third\n"], "new": ["THIRD\n"]}],
            },
        )
        assert outcome.kind == "executed"
        assert outcome.router_eligible is False
        assert "THIRD" in target.read_text(encoding="utf-8")

    def test_dispatch_hunk_edit_generated_refusal_is_not_router_eligible(self, dispatcher, tmp_path):
        """FR-M28-07 refusal flows through dispatch as a refusal — there is
        no code path from here to a model call (FR-M8-15)."""
        target = tmp_path / "app.min.js"
        target.write_text("var x=1;\n", encoding="utf-8")
        outcome = dispatcher.dispatch(
            "hunk_edit",
            {
                "path": str(target),
                "hunks": [{"context": [], "old": ["var x=1;\n"], "new": ["var y=1;\n"]}],
            },
        )
        assert outcome.kind == "refused"
        assert outcome.router_eligible is False
        assert "FR-M28-07" in outcome.reason
