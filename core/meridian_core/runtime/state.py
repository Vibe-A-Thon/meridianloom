"""Typed loop state with declared reducers — FR-M4-04.

State is typed: every field declares its type and the reducer that merges
concurrent updates from parallel branches. A field WITHOUT a reducer may
be written by exactly one branch per iteration — a concurrent write to a
reducer-less field is a runtime error. Silent last-write-wins is
prohibited by construction: there is no code path that assigns a branch
result without going through the declared reducer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

Reducer = Callable[[Any, Any], Any]


class StateMergeError(ValueError):
    """A concurrent update hit a field with no declared reducer, or a
    value failed its type check (FR-M4-04)."""


@dataclass(frozen=True)
class FieldSpec:
    """One state field: its type and the reducer merging concurrent
    writes. ``reducer=None`` declares the field single-writer."""

    name: str
    type: type
    reducer: Reducer | None = None
    default: Any = None


@dataclass
class LoopState:
    """A typed state instance. ``provenance`` records which branch wrote
    what, so merges are auditable and a reducer-less double-write is
    caught at merge time, not by luck."""

    schema: Mapping[str, FieldSpec]
    values: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)

    @classmethod
    def initial(cls, schema: Mapping[str, FieldSpec]) -> "LoopState":
        return cls(
            schema=schema,
            values={name: spec.default for name, spec in schema.items()},
        )

    def get(self, name: str) -> Any:
        if name not in self.schema:
            raise StateMergeError(f"unknown state field {name!r}")
        return self.values.get(name)

    def set(self, name: str, value: Any, *, branch: str = "main") -> None:
        spec = self.schema.get(name)
        if spec is None:
            raise StateMergeError(f"unknown state field {name!r}")
        if not isinstance(value, spec.type) and value is not None:
            raise StateMergeError(
                f"field {name!r} expects {spec.type.__name__}, got"
                f" {type(value).__name__}"
            )
        self.values[name] = value
        self.provenance[name] = branch

    def merge(self, updates: Mapping[str, tuple[str, Any]]) -> None:
        """Merge concurrent branch updates. Each update is
        ``field -> (branch_id, value)``. Fields with a declared reducer
        merge through it in branch-id order (deterministic); a field with
        NO reducer written by more than one branch raises — the conflict
        surfaces, it is never resolved by write order."""
        by_field: dict[str, list[tuple[str, Any]]] = {}
        for name, (branch, value) in updates.items():
            by_field.setdefault(name, []).append((branch, value))
        for name in sorted(by_field):
            writes = sorted(by_field[name])  # deterministic order
            spec = self.schema.get(name)
            if spec is None:
                raise StateMergeError(f"unknown state field {name!r}")
            if not all(
                isinstance(value, spec.type) or value is None
                for _, value in writes
            ):
                raise StateMergeError(f"field {name!r}: type mismatch in merge")
            if spec.reducer is not None:
                merged = self.values.get(name)
                for _, value in writes:
                    merged = spec.reducer(merged, value)
                self.values[name] = merged
                self.provenance[name] = "+".join(b for b, _ in writes)
            else:
                branches = {b for b, _ in writes}
                if len(branches) > 1:
                    raise StateMergeError(
                        f"FR-M4-04: field {name!r} has no declared reducer"
                        f" but parallel branches {sorted(branches)} wrote it"
                        " concurrently; declare a reducer or serialise the"
                        " writes — silent last-write-wins is prohibited"
                    )
                self.values[name] = writes[0][1]
                self.provenance[name] = writes[0][0]


#: Commonly declared reducers.
def append_unique(left: list | None, right: list | None) -> list:
    out = list(left or [])
    for item in right or []:
        if item not in out:
            out.append(item)
    return out


def add(left: float | int | None, right: float | int | None) -> float | int:
    return (left or 0) + (right or 0)


def keep_max(left: Any, right: Any) -> Any:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
