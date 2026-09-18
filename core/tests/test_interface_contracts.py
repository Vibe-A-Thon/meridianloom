"""TASK-340: FR-M22-02 interface contract generation and gate."""

from __future__ import annotations

import pytest

from meridian_core.interface_contracts import (
    ContractError,
    ContractTarget,
    generate_interface_contract,
    interface_contract_gate,
)


def test_multi_repo_story_generates_contract(tmp_path):
    path = generate_interface_contract(
        "X-1",
        (ContractTarget("api", "payments"), ContractTarget("web", "checkout")),
        tmp_path / "contracts",
    )
    text = path.read_text(encoding="utf-8")
    assert "openapi: 3.0.3" in text
    assert "/api/payments" in text and "/web/checkout" in text


def test_single_repo_refused(tmp_path):
    with pytest.raises(ContractError, match="multi-repo"):
        generate_interface_contract(
            "S-1", (ContractTarget("api", "payments"),), tmp_path
        )


def test_gate_blocks_multi_repo_without_contract(tmp_path):
    blocked = interface_contract_gate("X-1", repo_count=2, contracts_dir=tmp_path)
    assert blocked["passed"] is False
    assert "FR-M22-02" in blocked["reason"]
    ok = interface_contract_gate("S-1", repo_count=1, contracts_dir=tmp_path)
    assert ok["passed"] is True
    generate_interface_contract(
        "X-2", (ContractTarget("a", "x"), ContractTarget("b", "y")), tmp_path
    )
    unblocked = interface_contract_gate("X-2", repo_count=2, contracts_dir=tmp_path)
    assert unblocked["passed"] is True
