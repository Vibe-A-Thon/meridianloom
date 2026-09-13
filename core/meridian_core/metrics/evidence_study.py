"""The study record: what only people can supply to the evidence gate.

`docs/evidence-gate.md` fixes ten measures. The ledger answers part of three
of them. The rest exist only in the notes of the people running the study:
whether a gate stop was a real defect, what the baseline arm's rejection rate
was, whether anyone still uses the product at week eight, whether a Meridian
agent would plausibly do better than the team's own.

This module fixes the shape those answers take, so the gate *reads* them
instead of a person transcribing them into a verdict. Three rules shape it.

* **Absent is a state.** Every human section is optional. An absent section
  leaves its measure `unmeasured`, which is never satisfied (§5 of the
  preregistration).
* **Pseudonyms, not people.** Participants and reviewers are recorded by role
  or pseudonym. An `@` is refused wherever a person is named: an email address
  in a published study record is a disclosure nobody decided to make.
* **One source.** The schema is the constant below, and
  `python -m meridian_core.cli evidence-gate --print-schema` prints it. There
  is no second copy to drift from this one.

Zero model calls (FR-M36-07).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import jsonschema

_PERSON = {
    "type": "string",
    "minLength": 1,
    "not": {"pattern": "@"},
    "description": "a role or pseudonym, never a name or an email address",
}
_METHOD = {
    "type": "string",
    "minLength": 1,
    "description": "how this was measured, so a reader can weigh it",
}
_TIMESTAMP = {
    "type": "string",
    "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$",
}
_COUNTS = {
    "type": "object",
    "additionalProperties": False,
    "required": ["rejected", "proposed"],
    "properties": {
        "rejected": {"type": "integer", "minimum": 0},
        "proposed": {"type": "integer", "minimum": 0},
    },
}
_ARM = {"enum": ["A", "B", "C"]}
_STORY = {"type": "string", "minLength": 1}


def _array_of(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": required,
            "properties": properties,
        },
    }


#: The study record, JSON Schema draft 7 (the dialect core already validates).
STUDY_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "meridian-loom/evidence-study@1",
    "title": "Evidence gate study record",
    "description": (
        "Everything the evidence gate needs that the ledger cannot know. "
        "Scored by `python -m meridian_core.cli evidence-gate`."
    ),
    "type": "object",
    "additionalProperties": False,
    "required": ["studyId", "preregistration", "allocation"],
    "properties": {
        "$schema": {"type": "string"},
        "studyId": {"type": "string", "minLength": 1},
        "preregistration": {
            "type": "object",
            "additionalProperties": False,
            "required": ["registeredAt", "thresholdsDigest"],
            "properties": {
                "registeredAt": _TIMESTAMP,
                "thresholdsDigest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                "firstStoryMeasuredAt": {"anyOf": [_TIMESTAMP, {"type": "null"}]},
            },
        },
        # FR-M46-14: task allocation.
        "allocation": _array_of(
            {
                "storyId": _STORY,
                "arm": _ARM,
                "kind": {"enum": ["greenfield", "brownfield"]},
                "assignedBy": {"type": "string"},
            },
            ["storyId", "arm", "kind"],
        ),
        # FR-M46-15: exclusions are published, so they are recorded with a reason.
        "exclusions": _array_of(
            {"storyId": _STORY, "reason": {"type": "string", "minLength": 1}},
            ["storyId", "reason"],
        ),
        # FR-M46-14: agent and model configuration versions.
        "configuration": _array_of(
            {
                "agent": {"type": "string", "minLength": 1},
                "agentVersion": {"type": "string", "minLength": 1},
                "model": {"type": "string"},
                "modelVersion": {"type": "string"},
                "arms": {"type": "array", "items": _ARM},
            },
            ["agent", "agentVersion"],
        ),
        # P2: the baseline arm has no Meridian, so its figures come from the team.
        "armA": {
            "type": "object",
            "additionalProperties": False,
            "required": ["method", "rejectionRate"],
            "properties": {
                "method": _METHOD,
                "rejectionRate": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"greenfield": _COUNTS, "brownfield": _COUNTS},
                },
            },
        },
        # P3: the team's own change failure rate before Meridian.
        "baselineChangeFailureRate": {
            "type": "object",
            "additionalProperties": False,
            "required": ["rate", "method"],
            "properties": {
                "rate": {"type": "number", "minimum": 0, "maximum": 1},
                "method": _METHOD,
            },
        },
        # P1 and C1; FR-M46-14 independent review, defects caught, false blocks.
        "adjudications": _array_of(
            {
                "gateSequence": {"type": "integer", "minimum": 1},
                "realDefect": {"type": "boolean"},
                "caughtByAgentProcess": {"type": "boolean"},
                "reviewer": _PERSON,
                "reviewerRanGate": {"type": "boolean"},
                "blind": {"type": "boolean"},
                "note": {"type": "string"},
            },
            ["gateSequence", "realDefect", "caughtByAgentProcess", "reviewer", "reviewerRanGate"],
        ),
        # C2; FR-M46-14 human time. Minutes per gated pull request, per arm.
        "reviewTime": {
            "type": "object",
            "additionalProperties": False,
            "required": ["method", "armA", "armC"],
            "properties": {
                "method": _METHOD,
                "armA": {"type": "array", "items": {"type": "number", "minimum": 0}},
                "armC": {"type": "array", "items": {"type": "number", "minimum": 0}},
            },
        },
        # C3.
        "hygieneDetermination": {
            "type": "object",
            "additionalProperties": False,
            "required": ["systematicRubberStamping", "reviewer", "basis"],
            "properties": {
                "systematicRubberStamping": {"type": "boolean"},
                "reviewer": _PERSON,
                "basis": {"type": "string", "minLength": 1},
            },
        },
        # P4. Nothing in the product counts reads, by design; the team does.
        "provenanceQueries": {
            "type": "object",
            "additionalProperties": False,
            "required": ["method", "weeks"],
            "properties": {
                "method": _METHOD,
                "weeks": _array_of(
                    {
                        "week": {"type": "integer", "minimum": 1},
                        "engineers": _array_of(
                            {
                                "engineer": _PERSON,
                                "queries": {"type": "integer", "minimum": 0},
                            },
                            ["engineer", "queries"],
                        ),
                    },
                    ["week", "engineers"],
                ),
            },
        },
        # P5.
        "trustDecisionChanges": {
            "type": "object",
            "additionalProperties": False,
            "required": ["method", "instances"],
            "properties": {
                "method": _METHOD,
                "instances": _array_of(
                    {
                        "date": {"type": "string", "minLength": 1},
                        "changed": {
                            "enum": ["autonomy_tier", "agent_choice", "module_restriction"]
                        },
                        "description": {"type": "string", "minLength": 1},
                        "ledgerSequence": {"type": "integer", "minimum": 1},
                    },
                    ["date", "changed", "description"],
                ),
            },
        },
        # P6.
        "retention": {
            "type": "object",
            "additionalProperties": False,
            "required": ["originalTesters", "stillUsingAtWeek8", "method"],
            "properties": {
                "originalTesters": {"type": "integer", "minimum": 1},
                "stillUsingAtWeek8": {"type": "integer", "minimum": 0},
                "method": _METHOD,
            },
        },
        # O1.
        "orchestraCase": {
            "type": "object",
            "additionalProperties": False,
            "required": ["determination"],
            "properties": {
                "determination": {"enum": ["satisfied", "not_satisfied"]},
                "taskClass": {"type": "string"},
                "evidence": {"type": "string"},
                "namedAt": {"type": "string"},
            },
        },
        # FR-M46-14: accepted-change cost and 30-day regressions. Recorded and
        # published; the preregistered rule does not decide on them.
        "acceptedChangeCost": {
            "type": "object",
            "additionalProperties": False,
            "required": ["method"],
            "properties": {
                "method": _METHOD,
                "unit": {"type": "string"},
                "armA": {"type": "number", "minimum": 0},
                "armB": {"type": "number", "minimum": 0},
                "armC": {"type": "number", "minimum": 0},
            },
        },
        "regressions30Day": _array_of(
            {"storyId": _STORY, "regressed": {"type": "boolean"}, "note": {"type": "string"}},
            ["storyId", "regressed"],
        ),
        # FR-M46-04 (MVP-R5.3): five onboarding sessions and ten review tasks.
        "firstValue": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "sessions": _array_of(
                    {
                        "participant": _PERSON,
                        "minutesToFirstAnswer": {
                            "anyOf": [{"type": "number", "minimum": 0}, {"type": "null"}]
                        },
                        "note": {"type": "string"},
                    },
                    ["participant", "minutesToFirstAnswer"],
                ),
                "reviewTasks": _array_of(
                    {
                        "participant": _PERSON,
                        "identifiedRealBlockingRisk": {"type": "boolean"},
                        "note": {"type": "string"},
                    },
                    ["participant", "identifiedRealBlockingRisk"],
                ),
            },
        },
    },
}

#: FR-M46-14's recorded fields, and the section of the record that carries each.
RECORDED_FIELDS: dict[str, str] = {
    "task allocation": "allocation",
    "agent and model configuration versions": "configuration",
    "independent review": "adjudications",
    "human time": "reviewTime",
    "defects caught": "adjudications",
    "false blocks": "adjudications",
    "accepted-change cost": "acceptedChangeCost",
    "30-day regressions": "regressions30Day",
}


def _where(error: jsonschema.ValidationError) -> str:
    return "/" + "/".join(str(part) for part in error.absolute_path)


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_study(record: Any) -> list[str]:
    """Every reason `record` cannot be scored; empty when it can."""
    if not isinstance(record, dict):
        return ["the study record must be a JSON object"]

    problems: list[str] = []
    validator = jsonschema.Draft7Validator(STUDY_SCHEMA)
    for error in sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path)):
        if error.validator == "not" and "@" in str(error.validator_value):
            problems.append(
                f"{_where(error)}: a person is identified here. Record a role or "
                "pseudonym; an email address in a published study record is a "
                "disclosure nobody decided to make"
            )
        else:
            problems.append(f"{_where(error)}: {error.message}")
    if problems:
        return problems

    # What a schema cannot say.
    stories = [entry["storyId"] for entry in record["allocation"]]
    duplicates = sorted({story for story in stories if stories.count(story) > 1})
    if duplicates:
        problems.append(
            f"/allocation: {', '.join(duplicates)} allocated more than once; a "
            "story belongs to exactly one arm"
        )
    for entry in record.get("exclusions", []):
        if entry["storyId"] not in stories:
            problems.append(
                f"/exclusions: {entry['storyId']} is excluded but was never allocated"
            )
    retention = record.get("retention")
    if retention and retention["stillUsingAtWeek8"] > retention["originalTesters"]:
        problems.append(
            "/retention: more testers retained than there were originally"
        )
    case = record.get("orchestraCase")
    if case and case["determination"] == "satisfied" and not (
        str(case.get("taskClass") or "").strip() and str(case.get("evidence") or "").strip()
    ):
        problems.append(
            "/orchestraCase: O1 is satisfied only by a named task class with "
            "evidence; a determination on its own is an assertion"
        )
    registration = record["preregistration"]
    if _parse_time(registration["registeredAt"]) is None:
        problems.append("/preregistration/registeredAt: not a readable timestamp")
    return problems


def missing_recorded_fields(record: dict[str, Any] | None) -> list[str]:
    """FR-M46-14 fields the record does not carry. Published as missing data."""
    if not record:
        return sorted(RECORDED_FIELDS)
    return sorted(
        field for field, section in RECORDED_FIELDS.items() if not record.get(section)
    )


def registered_after_data(record: dict[str, Any]) -> bool:
    """True when the thresholds were registered after a story was measured."""
    registration = record.get("preregistration") or {}
    first = registration.get("firstStoryMeasuredAt")
    registered = _parse_time(str(registration.get("registeredAt") or ""))
    measured = _parse_time(str(first)) if first else None
    return bool(registered and measured and registered > measured)
