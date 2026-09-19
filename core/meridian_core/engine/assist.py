"""Assisted and generative modes (FR-M33-04/FR-M33-05) and model-call
ceilings (FR-M33-09) — the engine's model boundary.

The dispatcher (FR-M33-03) decides *whether* an action may reach the
router. This module is what happens on the other side of that decision,
with the model replaced by an injected client:

* **Assisted mode (FR-M33-04)** — the engine already ran its
  ``deterministicFirst`` capability (the dispatcher attached the partial
  result to the outcome). Here the engine builds the *bounded, schema-typed
  gap* — a :class:`GapRequest` declaring exactly what the model must
  produce, the schema name and document the return is validated against,
  and the engine's partial result — and hands it to the model client.
  A return is validated against the JSON schema AND the class's
  deterministic checks BEFORE it takes effect: an invalid return is
  rework — the validation errors are fed back to the model on the next
  attempt — or, once the bounded retry loop is exhausted, a refusal that
  names the errors. An invalid return is never silently accepted.
* **Generative mode (FR-M33-05)** — the engine cannot help; the whole
  task crosses to the model, but the output still does not take effect
  until it passes the class's ``validate`` list (named deterministic
  validators) and its schema. Failure is rework under the same bounded
  loop, then refusal with cause.
* **Model-call ceilings (FR-M33-09)** — per-class and global model-call
  budgets come from policy (``ceilings.model_calls`` in the action-class
  catalogue). A ceiling breach stops further model calls for that class
  (and globally, when the global ceiling is hit), records the breach in
  ``ModelCallBudget.breaches`` and on the outcome, and refuses with the
  breach named — the engine escalates rather than proceeds.

**Zero model calls (FR-M36-07).** The model is an injected
:class:`ModelClient` — a protocol, satisfied in tests by a fake. This
module imports no provider SDK and reads no model credentials; the
zero-model-call scanner (``core/tests/test_no_model_calls.py``) must stay
green.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

import jsonschema

from .catalogue import Catalogue
from .dispatch import DispatchOutcome, Dispatcher

__all__ = [
    "EngineModes",
    "GapRequest",
    "ModeResult",
    "ModelCallBudget",
    "ModelClient",
    "ModelResponse",
]

#: A deterministic validator: receives the model output, returns the list
#: of validation errors (empty = the output passes). Plain Python, no I/O.
Validator = Callable[[Any], Sequence[str]]

#: The default bounded rework loop (FR-M33-05): a first attempt plus this
#: many retries with the validation errors fed back, then refusal with
#: cause. Every attempt consumes the class's model-call ceiling.
DEFAULT_REWORK_LIMIT = 2


@dataclass(frozen=True)
class GapRequest:
    """The bounded, schema-typed gap the model is handed (FR-M33-04).

    This payload — not the whole task — is the model's entire brief:
    ``gap`` names exactly what must be produced, ``schema`` /
    ``schema_doc`` declare what the return is validated against, and
    ``partial`` carries the engine's deterministic result so the model
    fills a gap instead of redoing the work. On rework, ``attempt``
    counts the round and ``prior_errors`` carries the named validation
    errors the previous return failed with.
    """

    action_class: str
    gap: str
    schema: str
    schema_doc: Mapping[str, Any] | None
    partial: Any
    context: Mapping[str, Any]
    attempt: int = 0
    prior_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelResponse:
    """What the injected model client returned for one gap request.

    ``output`` is the model's proposed fill — it takes effect only after
    passing validation. ``latency_ms`` / ``cost_usd`` / tokens are the
    call's self-reported accounting, recorded for FR-M33-07 reporting.
    """

    output: Any
    latency_ms: int = 0
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    model_id: str = ""


@runtime_checkable
class ModelClient(Protocol):
    """The model seam — an injected callable/protocol, never a provider.

    The router workstream (Workstream C) supplies a real implementation
    behind this protocol; tests supply a fake. Anything implementing
    ``complete(request) -> ModelResponse`` satisfies it — zero model
    calls here (FR-M36-07): this protocol imports no provider SDK.
    """

    def complete(self, request: GapRequest) -> ModelResponse: ...


@dataclass
class ModelCallBudget:
    """Model-call ceilings from policy (FR-M33-09).

    Built from ``ceilings.model_calls`` in the action-class catalogue:
    ``global`` caps total model calls across every class, ``per_class``
    caps one class. Every consumed call is counted; a denied call is a
    breach — recorded here (denials are recorded, never silent, SEC-14)
    and surfaced on the outcome so the engine escalates rather than
    proceeds.
    """

    global_limit: int | None = None
    per_class: Mapping[str, int] = field(default_factory=dict)
    calls_by_class: dict[str, int] = field(default_factory=dict)
    total_calls: int = 0
    breaches: list[str] = field(default_factory=list)

    @classmethod
    def from_catalogue(cls, catalogue: Catalogue) -> "ModelCallBudget":
        """The budget declared by the catalogue's ``ceilings.model_calls``
        (absent ceilings mean unlimited — policy sets ceilings, not the
        engine)."""
        raw = catalogue.ceilings.get("model_calls") or {}
        global_raw = raw.get("global")
        per_class = raw.get("per_class") or {}
        return cls(
            global_limit=global_raw if isinstance(global_raw, int) else None,
            per_class={
                str(name): int(limit)
                for name, limit in per_class.items()
                if isinstance(limit, int)
            },
        )

    def allow(self, action_class: str) -> bool:
        """Whether one more model call may be made for the class — and
        records the breach when it may not."""
        class_used = self.calls_by_class.get(action_class, 0)
        class_limit = self.per_class.get(action_class)
        if class_limit is not None and class_used >= class_limit:
            self.breaches.append(
                f"model-call ceiling breached for '{action_class}': "
                f"per-class limit {class_limit} reached (FR-M33-09)"
            )
            return False
        if self.global_limit is not None and self.total_calls >= self.global_limit:
            self.breaches.append(
                f"model-call ceiling breached for '{action_class}': "
                f"global limit {self.global_limit} reached (FR-M33-09)"
            )
            return False
        return True

    def consume(self, action_class: str) -> None:
        """Count one model call against the class and the global total."""
        self.calls_by_class[action_class] = self.calls_by_class.get(action_class, 0) + 1
        self.total_calls += 1


@dataclass(frozen=True)
class ModeResult:
    """The engine-mode outcome of one action — the validated value that
    may take effect, or a refusal that names its cause."""

    action_class: str
    status: str  # executed|completed|refused|rework_refused|ceiling_breach
    dispatch: DispatchOutcome
    attempts: int = 0  # model calls made for this action
    value: Any = None  # the validated output (takes effect) — None unless status == completed
    validation_errors: tuple[str, ...] = ()
    latency_ms: int = 0
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    model_id: str = ""
    reason: str = ""


def _as_client(client: ModelClient | Callable[[GapRequest], Any]) -> ModelClient:
    """Accept either a ModelClient or a bare callable returning the raw
    output (wrapped into a zero-cost ModelResponse)."""
    if hasattr(client, "complete"):
        return client  # type: ignore[return-value]

    class _CallableClient:
        def complete(self, request: GapRequest) -> ModelResponse:
            return ModelResponse(output=client(request))

    return _CallableClient()


@dataclass
class EngineModes:
    """Assisted and generative execution on top of dispatch decisions.

    Wraps a :class:`Dispatcher`: deterministic outcomes return their
    result without any model call; assisted and generative outcomes run
    the bounded validate/rework loop against the injected model client.
    Outcomes are reported to an optional recorder (one record per action)
    for FR-M33-07 per-class reporting.

    ``schemas`` maps a schema name (as named in the catalogue) to its
    JSON Schema document; a model output claimed against an unregistered
    schema is refused with the schema named — fail-closed, never silently
    accepted. ``validators`` maps the names in a generative class's
    ``validate`` list to deterministic checks; an unregistered validator
    name is likewise a named, fail-closed refusal. ``checks`` optionally
    binds extra per-class deterministic checks for assisted returns
    (FR-M33-04: schema AND deterministic checks).
    """

    dispatcher: Dispatcher
    client: ModelClient | Callable[[GapRequest], Any]
    schemas: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    validators: Mapping[str, Validator] = field(default_factory=dict)
    checks: Mapping[str, Sequence[Validator]] = field(default_factory=dict)
    budget: ModelCallBudget = field(default_factory=ModelCallBudget)
    rework_limit: int = DEFAULT_REWORK_LIMIT
    recorder: Any = None  # object with .record(DispatchRecord, **context)

    def run(
        self,
        action_class: str,
        payload: Mapping[str, Any] | None = None,
        *,
        story_id: str = "engine",
        phase: str = "engine",
    ) -> ModeResult:
        """Execute one action end to end. Deterministic classes never see
        a model call; assisted/generative classes cross to the injected
        client under the ceilings and the bounded rework loop."""
        client = _as_client(self.client)
        payload = payload or {}
        outcome = self.dispatcher.dispatch(action_class, payload)

        if outcome.kind == "executed":
            result = ModeResult(
                action_class=action_class,
                status="executed",
                dispatch=outcome,
                value=outcome.result,
                reason=outcome.reason,
            )
            self._record(result, story_id, phase)
            return result
        if outcome.kind == "refused":
            result = ModeResult(
                action_class=action_class,
                status="refused",
                dispatch=outcome,
                reason=outcome.reason,
            )
            self._record(result, story_id, phase)
            return result

        # assisted | generative: the engine declares the gap (assisted
        # carries the deterministic-first partial result), the model fills
        # it, the engine validates before anything takes effect.
        gap = outcome.gap or outcome.schema or "produce the class output"
        request = GapRequest(
            action_class=action_class,
            gap=gap,
            schema=outcome.schema or "",
            schema_doc=self.schemas.get(outcome.schema or ""),
            partial=outcome.result,
            context=dict(payload),
        )
        attempts = 0
        errors: tuple[str, ...] = ()
        latency_ms = 0
        cost_usd = 0.0
        tokens_in = 0
        tokens_out = 0
        model_id = ""
        for attempt in range(self.rework_limit + 1):
            if not self.budget.allow(action_class):
                breach = self.budget.breaches[-1]
                result = ModeResult(
                    action_class=action_class,
                    status="ceiling_breach",
                    dispatch=outcome,
                    attempts=attempts,
                    validation_errors=errors,
                    latency_ms=latency_ms,
                    cost_usd=cost_usd,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    model_id=model_id,
                    reason=breach
                    if not errors
                    else f"{breach}; rework aborted with errors: {'; '.join(errors)}",
                )
                self._record(result, story_id, phase)
                return result
            request = GapRequest(
                action_class=request.action_class,
                gap=request.gap,
                schema=request.schema,
                schema_doc=request.schema_doc,
                partial=request.partial,
                context=request.context,
                attempt=attempt,
                prior_errors=errors,
            )
            started = time.monotonic()
            response = client.complete(request)
            latency_ms += int((time.monotonic() - started) * 1000)
            self.budget.consume(action_class)
            attempts += 1
            cost_usd += response.cost_usd
            tokens_in += response.tokens_in
            tokens_out += response.tokens_out
            model_id = response.model_id or model_id
            errors = tuple(
                self._validate(outcome, response.output)
            )
            if not errors:
                result = ModeResult(
                    action_class=action_class,
                    status="completed",
                    dispatch=outcome,
                    attempts=attempts,
                    value=response.output,
                    latency_ms=latency_ms,
                    cost_usd=cost_usd,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    model_id=model_id,
                    reason="model output validated; takes effect (FR-M33-04/FR-M33-05)",
                )
                self._record(result, story_id, phase)
                return result
        result = ModeResult(
            action_class=action_class,
            status="rework_refused",
            dispatch=outcome,
            attempts=attempts,
            validation_errors=errors,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model_id=model_id,
            reason="rework loop exhausted: model output failed validation and was "
            "refused with cause — the invalid output never takes effect "
            "(FR-M33-04/FR-M33-05): "
            + "; ".join(errors),
        )
        self._record(result, story_id, phase)
        return result

    def _validate(
        self, outcome: DispatchOutcome, output: Any
    ) -> list[str]:
        """Deterministic validation BEFORE the output takes effect: the
        named schema, then the class's deterministic checks. Every error
        is named; an unregistered schema or validator name is fail-closed
        (the output is refused, never silently accepted)."""
        errors: list[str] = []
        schema_name = outcome.schema or ""
        if schema_name:
            schema_doc = self.schemas.get(schema_name)
            if schema_doc is None:
                errors.append(
                    f"schema '{schema_name}' not registered — output refused (fail-closed)"
                )
            else:
                for error in sorted(
                    jsonschema.Draft7Validator(schema_doc).iter_errors(output),
                    key=lambda e: (list(e.absolute_path), e.message),
                ):
                    path = "/".join(str(part) for part in error.absolute_path)
                    where = f"{path}: " if path else ""
                    errors.append(f"schema '{schema_name}': {where}{error.message}")
        else:
            errors.append("no output schema named in policy — output refused (fail-closed)")
        for name in outcome.validate:
            validator = self.validators.get(name)
            if validator is None:
                errors.append(
                    f"validator '{name}' not registered — output refused (fail-closed)"
                )
                continue
            errors.extend(f"validator '{name}': {e}" for e in validator(output))
        for check in self.checks.get(outcome.action_class, ()):
            errors.extend(f"deterministic check: {e}" for e in check(output))
        return errors

    def _record(self, result: ModeResult, story_id: str, phase: str) -> None:
        if self.recorder is None:
            return
        from .reporting import DispatchRecord

        self.recorder.record(
            DispatchRecord(
                action_class=result.action_class,
                mode=result.dispatch.kind,
                status=result.status,
                attempts=result.attempts,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                validation_errors=result.validation_errors,
                why_llm=result.dispatch.why_llm,
                rules_matched=result.dispatch.rules_matched,
            ),
            story_id=story_id,
            phase=phase,
        )
