"""OTLP JSON parsing for vendor OTel exports (FR-M35-02 second tier).

Parses OTLP/HTTP JSON export payloads the user points Meridian at (a
directory of ``*.json`` / ``*.jsonl`` files written by an agent's OTel
exporter). No live collector is required — the observer reads recorded
exports only.

Format drift (NFR-32): a file that parses as JSON but matches no known
OTLP envelope raises :class:`TelemetryFormatError`, which the fallback
chain turns into the documented downgrade with a visible warning. A valid
OTLP envelope with no matching spans is simply "no evidence" (None).
Pure stdlib; zero model calls (FR-M36-07).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import TelemetryFormatError

# OTLP JSON value variants carry the scalar under a type-named key, e.g.
# {"key": "service.name", "value": {"stringValue": "claude-code"}}.
_VALUE_KEYS = (
    "stringValue",
    "intValue",
    "doubleValue",
    "boolValue",
    "arrayValue",
    "kvlistValue",
    "bytesValue",
)


@dataclass(frozen=True)
class Span:
    name: str
    trace_id: str
    started_at: str  # ISO 8601 UTC
    attributes: dict[str, Any] = field(default_factory=dict)
    resource_attributes: dict[str, Any] = field(default_factory=dict)


def _attrs_to_dict(attributes: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not isinstance(attributes, list):
        return result
    for entry in attributes:
        if not isinstance(entry, dict) or "key" not in entry:
            continue
        value = entry.get("value")
        if isinstance(value, dict):
            for key in _VALUE_KEYS:
                if key in value:
                    result[entry["key"]] = value[key]
                    break
            else:
                result[entry["key"]] = value
        else:
            result[entry["key"]] = value
    return result


def _span_from_raw(raw: dict[str, Any], resource_attrs: dict[str, Any]) -> Span | None:
    if not isinstance(raw, dict) or "name" not in raw:
        return None
    started = raw.get("startTimeUnixNano")
    if started is None:
        return None
    try:
        started_iso = datetime.fromtimestamp(int(started) / 1e9, tz=timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError) as error:
        raise TelemetryFormatError(
            f"span startTimeUnixNano not parseable: {started!r}"
        ) from error
    return Span(
        name=str(raw["name"]),
        trace_id=str(raw.get("traceId", "")),
        started_at=started_iso,
        attributes=_attrs_to_dict(raw.get("attributes")),
        resource_attributes=resource_attrs,
    )


def parse_otlp_payload(payload: Any) -> list[Span]:
    """One decoded JSON document -> spans.

    Accepts the OTLP/HTTP export envelope (``resourceSpans``), a bare span
    list, or a single span object. Raises TelemetryFormatError when the
    document is JSON but shaped like nothing OTLP this adapter knows —
    that is the vendor-drift signal.
    """
    if isinstance(payload, dict) and "resourceSpans" in payload:
        spans: list[Span] = []
        resource_spans = payload["resourceSpans"]
        if not isinstance(resource_spans, list):
            raise TelemetryFormatError("resourceSpans is not a list")
        for resource_span in resource_spans:
            if not isinstance(resource_span, dict):
                raise TelemetryFormatError("resourceSpans entry is not an object")
            resource_attrs = _attrs_to_dict(
                (resource_span.get("resource") or {}).get("attributes")
            )
            scope_spans = resource_span.get("scopeSpans") or resource_span.get(
                "instrumentationLibrarySpans"
            )
            if scope_spans is None:
                raise TelemetryFormatError(
                    "resourceSpans entry has no scopeSpans — export shape changed"
                )
            if not isinstance(scope_spans, list):
                raise TelemetryFormatError("scopeSpans is not a list")
            for scope_span in scope_spans:
                if not isinstance(scope_span, dict) or not isinstance(
                    scope_span.get("spans"), list
                ):
                    raise TelemetryFormatError("scopeSpans entry shape changed")
                for raw in scope_span["spans"]:
                    span = _span_from_raw(raw, resource_attrs)
                    if span is not None:
                        spans.append(span)
        return spans
    if isinstance(payload, list):
        spans = []
        for raw in payload:
            span = _span_from_raw(raw, {})
            if span is not None:
                spans.append(span)
        if spans or not payload:
            return spans
        raise TelemetryFormatError("span list entries lack name/startTimeUnixNano")
    if isinstance(payload, dict) and "name" in payload and "startTimeUnixNano" in payload:
        span = _span_from_raw(payload, {})
        return [span] if span else []
    raise TelemetryFormatError(
        "JSON document is not an OTLP export, span list, or span object"
    )


def load_spans(path: Path) -> list[Span]:
    """Parse one export file (.json or .jsonl) into spans."""
    text = path.read_text(encoding="utf-8", errors="replace")
    stripped = text.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        # NDJSON: one JSON document per line (e.g. an exporter appending
        # each batch). If that fails too, it is vendor drift.
        lines = [line for line in stripped.splitlines() if line.strip()]
        spans: list[Span] = []
        try:
            for line in lines:
                spans.extend(parse_otlp_payload(json.loads(line)))
        except json.JSONDecodeError as error:
            raise TelemetryFormatError(
                f"export file is neither JSON nor NDJSON: {error}"
            ) from error
        return spans
    return parse_otlp_payload(payload)


def export_dir_spans(otel_dir: Path) -> list[Span]:
    """All spans across every export file in a directory.

    Missing/empty directory means the tier is simply unavailable (the
    caller maps that to None, not to vendor drift).
    """
    if not otel_dir.is_dir():
        return []
    spans: list[Span] = []
    for path in sorted(otel_dir.iterdir()):
        if path.suffix.lower() not in (".json", ".jsonl"):
            continue
        if not path.is_file():
            continue
        spans.extend(load_spans(path))
    return spans
