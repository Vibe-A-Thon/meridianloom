"""Rule-based ambiguity detection capability (FR-M33-02; FR-M33-04).

The deterministic-first phase of the assisted ``detect_ambiguity`` class:
scans story acceptance criteria with fixed, declarative rules and flags
the criterion with the rule id that fired —

* ``ambiguity.vague_quantifier`` — an unmeasurable quantifier
  ("fast", "soon", "asap", "user-friendly", …) appears in the text;
* ``ambiguity.missing_actor`` — a criterion starts with a bare modal
  ("Shall …", "Must …") or a modal-without-subject pattern ("shall be
  able to"), i.e. no actor owns the requirement;
* ``ambiguity.missing_condition`` — a temporal/quantified claim ("within
  N days", "when …", deadlines) carries no condition or trigger at all
  (no "when/if/after/before/unless/once" and no actor-supplied context).

A ``RuleSet`` (FR-M33-06 learned/rules) supplied on the payload is
evaluated against the story payload too: learned rules that match ride
along on the flags with their own ids. What never happens here is the
resolution proposal — that is the assisted class's bounded gap
(``gap: propose resolution``, declared in the catalogue).

Zero model calls: lexicon and regex application only.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .capabilities import CapabilityOutcome
from .rules import RuleSet

__all__ = ["RuleAmbiguityCapability"]

_CAPABILITY_NAME = "rule_ambiguity"

#: Unmeasurable quantifiers / vague quality words (lowercased, matched on
#: word boundaries). Fixed lexicon — extension happens via learned/rules.
_VAGUE_QUANTIFIERS = (
    "fast",
    "quickly",
    "soon",
    "asap",
    "responsive",
    "seamless",
    "user-friendly",
    "intuitive",
    "robust",
    "scalable",
    "efficiently",
    "easily",
)

_MODAL_START = re.compile(r"^\s*(?:the\s+\w+\s+)?(shall|must|should|will|may)\b", re.IGNORECASE)
_MODAL_NO_SUBJECT = re.compile(r"\b(?:shall|must|should)\s+be\s+able\s+to\b", re.IGNORECASE)
_CONDITION_WORDS = re.compile(
    r"\b(when|if|after|before|unless|once|until|given|while)\b", re.IGNORECASE
)


class RuleAmbiguityCapability:
    """The ``rule_ambiguity`` capability — the ``deterministicFirst``
    phase of the assisted ``detect_ambiguity`` class.

    Payload: ``{criteria}`` — a list of ``{id, text}`` mappings (the
    story's acceptance criteria); optional ``story`` mapping and
    ``rules`` RuleSet for the learned-rules pass.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        criteria = action.get("criteria")
        if not isinstance(criteria, list) or any(
            not isinstance(c, Mapping) or not isinstance(c.get("text"), str) for c in criteria
        ):
            return CapabilityOutcome(
                handled=False, reason="'criteria' must be a list of {id, text} mappings"
            )

        flags: list[dict[str, Any]] = []
        for criterion in criteria:
            criterion_id = str(criterion.get("id"))
            text = criterion["text"]
            flags.extend(self._scan(criterion_id, text))

        # FR-M33-06: learned/rules that match the payload ride along (the
        # dispatcher consults the same ruleset against the same payload).
        rules = action.get("rules")
        learned: list[str] = []
        if isinstance(rules, RuleSet):
            learned = [
                rule.id for rule in rules.matching("detect_ambiguity", dict(action))
            ]

        return CapabilityOutcome(
            handled=True,
            result={
                "flags": flags,
                "flagged_criteria": sorted({f["criterion"] for f in flags}),
                "learned_rules_matched": learned,
                "gap": "propose resolution",  # the catalogue-declared bounded gap
            },
            reason=f"{len(flags)} ambiguity flag(s) from fixed rules (FR-M33-02); "
            f"resolution proposal is the assisted gap (FR-M33-04)",
        )

    @staticmethod
    def _scan(criterion_id: str, text: str) -> list[dict[str, Any]]:
        flags: list[dict[str, Any]] = []
        lowered = text.lower()
        for quantifier in _VAGUE_QUANTIFIERS:
            match = re.search(rf"\b{re.escape(quantifier)}\b", lowered)
            if match:
                flags.append(
                    {
                        "criterion": criterion_id,
                        "rule": "ambiguity.vague_quantifier",
                        "span": match.group(0),
                        "detail": f"unmeasurable quantifier '{match.group(0)}' "
                        f"at offset {match.start()}",
                    }
                )
        if _MODAL_START.match(text) or _MODAL_NO_SUBJECT.search(text):
            flags.append(
                {
                    "criterion": criterion_id,
                    "rule": "ambiguity.missing_actor",
                    "span": None,
                    "detail": "criterion is modal without a subject actor "
                    "(FR-M25-02: who is unspecified)",
                }
            )
        if _CONDITION_WORDS.search(text) is None and re.search(
            r"\bwithin\b|\bdeadline\b|\bby\s+\d", lowered
        ):
            flags.append(
                {
                    "criterion": criterion_id,
                    "rule": "ambiguity.missing_condition",
                    "span": None,
                    "detail": "temporal/quantified claim carries no condition or trigger",
                }
            )
        return flags
