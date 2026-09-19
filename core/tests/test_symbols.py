"""tree-sitter line→symbol mapping (FR-M33-02 subset, F0 Workstream C task 14).

Provenance answers name the enclosing function/class ("PaymentController.
submit"), not only a line number. Parsing is pure tree-sitter — structural
and deterministic, zero model calls (FR-M36-07). Languages that are not
registered degrade gracefully: ``symbol`` (and ``language``) come back null
and never raise; even parse errors in a registered language yield the best
enclosing-symbol chain tree-sitter can recover.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian_core.attribution import symbols

JAVA_SOURCE = """\
package com.example.payments;

public class PaymentController {
    private final Ledger ledger;

    public PaymentController(Ledger ledger) {
        this.ledger = ledger;
    }

    public Receipt submit(Order order) {
        validate(order);
        Receipt receipt = charge(order);
        return receipt;
    }

    static class Defaults {
        static Receipt emptyReceipt() {
            return Receipt.NONE;
        }
    }
}
"""

PYTHON_SOURCE = """\
\"\"\"Fixture module.\"\"\"


def top_level():
    def inner():
        return 1
    return inner


class Service:
    def handle(self):
        return top_level()
"""


@pytest.fixture()
def java_file(tmp_path: Path) -> Path:
    target = tmp_path / "PaymentController.java"
    target.write_text(JAVA_SOURCE, encoding="utf-8")
    return target


@pytest.fixture()
def python_file(tmp_path: Path) -> Path:
    target = tmp_path / "service.py"
    target.write_text(PYTHON_SOURCE, encoding="utf-8")
    return target


def line_of(source: str, needle: str) -> int:
    for index, text in enumerate(source.splitlines(), start=1):
        if needle in text:
            return index
    raise AssertionError(f"needle not found: {needle}")


class TestJava:
    def test_method_line_names_enclosing_class_and_method(self, java_file):
        result = symbols.symbol_at(
            java_file, line_of(JAVA_SOURCE, "Receipt receipt = charge")
        )
        assert result.language == "java"
        assert result.symbol == "PaymentController.submit"

    def test_constructor_line(self, java_file):
        result = symbols.symbol_at(
            java_file, line_of(JAVA_SOURCE, "this.ledger = ledger;")
        )
        assert result.symbol == "PaymentController.PaymentController"

    def test_class_body_line_outside_any_method(self, java_file):
        result = symbols.symbol_at(java_file, line_of(JAVA_SOURCE, "private final"))
        assert result.symbol == "PaymentController"

    def test_nested_class_method_is_fully_qualified(self, java_file):
        result = symbols.symbol_at(
            java_file, line_of(JAVA_SOURCE, "return Receipt.NONE;")
        )
        assert result.symbol == "PaymentController.Defaults.emptyReceipt"

    def test_package_line_has_no_enclosing_symbol(self, java_file):
        result = symbols.symbol_at(java_file, 1)
        assert result.symbol is None
        assert result.language == "java"


class TestPython:
    def test_method_names_class_and_method(self, python_file):
        result = symbols.symbol_at(
            python_file, line_of(PYTHON_SOURCE, "return top_level()")
        )
        assert result.language == "python"
        assert result.symbol == "Service.handle"

    def test_nested_function_is_qualified_by_parent(self, python_file):
        result = symbols.symbol_at(python_file, line_of(PYTHON_SOURCE, "return 1"))
        assert result.symbol == "top_level.inner"

    def test_top_level_function(self, python_file):
        result = symbols.symbol_at(python_file, line_of(PYTHON_SOURCE, "return inner"))
        assert result.symbol == "top_level"


class TestGracefulDegradation:
    def test_unregistered_language_reports_null_symbol(self, tmp_path):
        target = tmp_path / "main.rs"
        target.write_text("fn main() {\n    let x = 1;\n}\n", encoding="utf-8")
        result = symbols.symbol_at(target, 2)
        assert result.symbol is None
        assert result.language is None

    def test_plain_text_reports_null_symbol(self, tmp_path):
        target = tmp_path / "notes.txt"
        target.write_text("nothing parseable\n", encoding="utf-8")
        result = symbols.symbol_at(target, 1)
        assert result.symbol is None
        assert result.language is None

    def test_garbage_in_registered_language_still_resolves(self, tmp_path):
        target = tmp_path / "Broken.java"
        target.write_text(
            "class Broken {\n  void ok() {\n    !@# nonsense\n  }\n}\n",
            encoding="utf-8",
        )
        result = symbols.symbol_at(target, 3)
        assert result.symbol == "Broken.ok"

    def test_crlf_source_maps_lines_correctly(self, tmp_path):
        target = tmp_path / "crlf.java"
        target.write_bytes(JAVA_SOURCE.replace("\n", "\r\n").encode("utf-8"))
        result = symbols.symbol_at(
            target, line_of(JAVA_SOURCE, "Receipt receipt = charge")
        )
        assert result.symbol == "PaymentController.submit"

    def test_missing_file_is_a_clean_error(self, tmp_path):
        with pytest.raises(symbols.SymbolsError, match="does not exist"):
            symbols.symbol_at(tmp_path / "nope.py", 1)

    def test_line_outside_file_range(self, python_file):
        result = symbols.symbol_at(python_file, 10_000)
        assert result.symbol is None


class TestSymbolRpc:
    def _server(self, repo):
        from meridian_core import protocol
        from meridian_core.server import SidecarServer

        server = SidecarServer()
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "pytest",
                    "workspaceDir": str(repo),
                },
            }
        )
        assert "result" in response
        return server

    def test_symbol_round_trip(self, repo, java_file):
        server = self._server(repo)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "attrib/symbol",
                "params": {
                    "repoPath": str(repo),
                    "path": java_file.name,
                    "line": line_of(JAVA_SOURCE, "Receipt receipt = charge"),
                },
            }
        )
        assert "result" in response, response
        result = response["result"]
        assert result["symbol"] == "PaymentController.submit"
        assert result["language"] == "java"
        assert result["path"] == java_file.name

    def test_unknown_extension_round_trip_null_symbol(self, repo, tmp_path):
        server = self._server(repo)
        (repo / "notes.txt").write_text("x\n", encoding="utf-8")
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "attrib/symbol",
                "params": {"repoPath": str(repo), "path": "notes.txt", "line": 1},
            }
        )
        assert "result" in response, response
        assert response["result"]["symbol"] is None
        assert response["result"]["language"] is None

    def test_missing_file_is_a_params_error(self, repo):
        from meridian_core import protocol

        server = self._server(repo)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "attrib/symbol",
                "params": {"repoPath": str(repo), "path": "nope.py", "line": 1},
            }
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS

    def test_path_escape_refused(self, repo):
        from meridian_core import protocol

        server = self._server(repo)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "attrib/symbol",
                "params": {"repoPath": str(repo), "path": "../outside.py", "line": 1},
            }
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
