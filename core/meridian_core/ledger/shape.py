"""One evidence shape, from two editors and two SCM providers (AC-50, FR-M43-15).

AC-50 asks one customer to work the same change in two supported editors, merge
it through two SCM providers, and show that both bundles verify with the open
verifier on a clean machine **and carry the same evidence schema**. Verifying is
`verify.py`'s job. This module is the other half: saying whether two bundles
have the same shape, precisely enough that "they look the same" is not the
answer anybody writes down.

Two bundles of the same change legitimately differ in almost every value, such
as timestamps, keys, sequence numbers, vendors and who approved. What must not
differ is what a reader needs in order to interpret either one: the format and
schema versions, the sections present, the fields an entry carries and the
JSON type of each, the redaction profiles that say what an absent field means,
and the enforcement and compliance sections that say what bound the change.

A field that is `null` in every entry of one bundle and a string in the other
is not a difference of shape: one editor simply had nothing to record there.
A field that is a string in one and a number in the other is a difference,
because a reader cannot parse both with one reading.

Zero model calls (FR-M36-07). Reads JSON; executes nothing.
"""

from __future__ import annotations

from typing import Any


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _keys(section: Any) -> list[str] | None:
    return sorted(section) if isinstance(section, dict) else None


def evidence_shape(bundle: dict[str, Any]) -> dict[str, Any]:
    """The parts of a bundle a reader needs to interpret it, without values."""
    fields: dict[str, set[str]] = {}
    entries = bundle.get("entries") if isinstance(bundle.get("entries"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key, value in entry.items():
            fields.setdefault(key, set()).add(_json_type(value))
    redaction = bundle.get("redaction") if isinstance(bundle.get("redaction"), dict) else {}
    profiles = redaction.get("profiles") if isinstance(redaction.get("profiles"), dict) else {}
    return {
        "formatVersion": bundle.get("formatVersion"),
        "schemaVersion": bundle.get("schemaVersion"),
        "sections": sorted(bundle),
        "entries": len(entries),
        "entryFields": {key: sorted(types) for key, types in sorted(fields.items())},
        "redaction": {
            "keys": _keys(redaction),
            "profiles": {name: _keys(profile) for name, profile in sorted(profiles.items())},
        },
        "enforcement": _keys(bundle.get("enforcement")),
        "compliance": _keys(bundle.get("compliance")),
        "proofs": _keys(bundle.get("proofs")),
        "signerAlgorithm": (bundle.get("signer") or {}).get("algorithm")
        if isinstance(bundle.get("signer"), dict)
        else None,
    }


def shape_differences(first: dict[str, Any], second: dict[str, Any]) -> list[str]:
    """Every way two shapes differ that a reader would have to account for."""
    differences: list[str] = []
    for key in ("formatVersion", "schemaVersion", "signerAlgorithm"):
        if first[key] != second[key]:
            differences.append(f"{key}: {first[key]!r} against {second[key]!r}")

    for key in ("sections", "enforcement", "compliance", "proofs"):
        a, b = first[key], second[key]
        if a == b:
            continue
        if a is None or b is None:
            differences.append(f"{key}: present in one bundle only")
            continue
        only_first = sorted(set(a) - set(b))
        only_second = sorted(set(b) - set(a))
        if only_first:
            differences.append(f"{key}: only the first has {', '.join(only_first)}")
        if only_second:
            differences.append(f"{key}: only the second has {', '.join(only_second)}")

    if first["redaction"] != second["redaction"]:
        differences.append(
            "redaction: the collection profiles differ, so an absent field does not "
            "mean the same thing in both bundles"
        )

    # Entry fields. Only comparable when both bundles have entries: an empty
    # bundle has no field vocabulary to disagree with.
    if first["entries"] and second["entries"]:
        a_fields, b_fields = first["entryFields"], second["entryFields"]
        for name in sorted(set(a_fields) - set(b_fields)):
            differences.append(f"entry field {name}: only in the first bundle")
        for name in sorted(set(b_fields) - set(a_fields)):
            differences.append(f"entry field {name}: only in the second bundle")
        for name in sorted(set(a_fields) & set(b_fields)):
            a_types = set(a_fields[name]) - {"null"}
            b_types = set(b_fields[name]) - {"null"}
            if a_types and b_types and a_types != b_types:
                differences.append(
                    f"entry field {name}: {'/'.join(sorted(a_types))} against "
                    f"{'/'.join(sorted(b_types))}"
                )
    elif first["entries"] != second["entries"] and not (first["entries"] and second["entries"]):
        differences.append(
            "entries: one bundle is empty, so there is no evidence in it to compare"
        )
    return differences
