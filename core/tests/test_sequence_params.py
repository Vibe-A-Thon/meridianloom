"""Sequence filters are validated at the boundary, once, for every method.

Twenty RPCs take ``fromSequence`` / ``toSequence`` / ``afterSequence`` /
``sequence``. None of them validated it. A string reached SQLite as a bound
parameter, where cross-type comparison does not fail — it just matches
nothing — so ``fromSequence: "abc"`` produced a trust score computed over the
wrong rows and returned it as though it meant something.

That is the worst failure this product can have. A crash is loud; a figure
that is quietly wrong gets pasted into a board deck. So the check lives at the
dispatch boundary, refuses with INVALID_PARAMS, and applies to any method that
names its parameter the same way — including ones written after this.
"""

from __future__ import annotations

import pytest

from meridian_core import protocol
from meridian_core.server import _check_sequence_params, _MAX_SEQUENCE, _RpcError


def refusal(params: dict) -> _RpcError:
    with pytest.raises(_RpcError) as caught:
        _check_sequence_params("trust/score", params)
    return caught.value


class TestItRefusesWhatCannotAddressARow:
    @pytest.mark.parametrize(
        "value",
        ["abc", "", "12", 1.5, [], {}, True, False],
        ids=["text", "empty", "numeric-string", "float", "list", "dict", "true", "false"],
    )
    def test_a_non_integer_is_refused_not_coerced(self, value):
        # "12" is the interesting one: coercing it would be friendly right up
        # until the day a caller sends "12abc" and gets a silent zero.
        error = refusal({"fromSequence": value})
        assert error.code == protocol.INVALID_PARAMS
        assert "whole number" in error.message

    def test_booleans_are_refused_even_though_python_calls_them_ints(self):
        # isinstance(True, int) is True. Without the explicit check,
        # fromSequence: true would silently mean sequence 1.
        error = refusal({"fromSequence": True})
        assert "bool" in error.message

    @pytest.mark.parametrize("value", [-1, -(2**63), _MAX_SEQUENCE + 1])
    def test_a_sequence_no_row_can_carry_is_refused(self, value):
        error = refusal({"toSequence": value})
        assert error.code == protocol.INVALID_PARAMS
        assert "No ledger row can carry" in error.message

    def test_the_message_names_the_field_and_the_method(self):
        error = refusal({"afterSequence": "nope"})
        assert "afterSequence" in error.message
        assert "trust/score" in error.message

    def test_it_says_why_it_refuses_rather_than_only_that_it_did(self):
        # The reason is the point: a caller who sees "invalid parameter" fixes
        # the call; a caller who sees "refusing rather than computing a figure
        # over the wrong rows" understands what was at stake.
        assert "wrong rows" in refusal({"fromSequence": "x"}).message


class TestItLetsLegitimateCallsThrough:
    @pytest.mark.parametrize("value", [0, 1, 4402, _MAX_SEQUENCE])
    def test_every_addressable_sequence_passes(self, value):
        _check_sequence_params("ledger.query", {"fromSequence": value})

    def test_absent_and_null_are_not_filters(self):
        _check_sequence_params("ledger.query", {})
        _check_sequence_params("ledger.query", {"fromSequence": None})

    def test_it_ignores_parameters_that_are_not_sequences(self):
        # storyId "abc" is perfectly valid; only sequence-named fields are
        # this check's business.
        _check_sequence_params(
            "trust/score", {"actorId": "claude-code", "storyId": "abc", "limit": "10"}
        )

    def test_a_non_dict_params_payload_is_left_to_the_handler(self):
        # Malformed envelopes are the protocol layer's problem, not this one's.
        _check_sequence_params("ledger.query", None)
        _check_sequence_params("ledger.query", [1, 2, 3])


class TestEveryMethodInTheRegistryIsCovered:
    def test_the_convention_holds_across_the_schema(self):
        """A sequence parameter anywhere in the registry is caught by name.

        This is what makes one boundary check equivalent to twenty handler
        checks — and it fails if someone adds `seqFrom` or `startSeq` instead,
        which is the point: the convention is load-bearing now.
        """
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        schema = json.loads(
            (root / "shared" / "schema" / "methods.json").read_text(encoding="utf-8")
        )
        defs = schema["$defs"]
        offenders: list[str] = []
        for name, method in schema["x-methods"].items():
            ref = (method.get("params") or {}).get("$ref", "")
            key = ref.rsplit("/", 1)[-1]
            for prop in (defs.get(key) or {}).get("properties", {}):
                looks_like_a_sequence = "equence" in prop or prop.lower().endswith("seq")
                caught = prop.endswith(("Sequence", "sequence"))
                if looks_like_a_sequence and not caught:
                    offenders.append(f"{name}.{prop}")
        assert not offenders, (
            "these parameters look like ledger sequences but the boundary check "
            f"will not see them: {', '.join(offenders)}. Rename them to end in "
            "'Sequence', or the silently-wrong-figure bug comes back for them."
        )
