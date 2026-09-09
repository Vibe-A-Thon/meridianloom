"""Predictable pricing pack (FR-M39-04; F1 Workstream F task 29).

Meridian's own pricing model is predictable by design — the Flight
Recorder tier makes no model calls and has no usage-based cost; the
Governor and Orchestra tiers report their own model spend in the same
ledger as everyone else's. For every *other* vendor, recorded tokens
multiply a configured rate: token rates live in the pricing pack
(``policy/pricing.yaml`` in the repository, a workspace override at
``.meridian/policy/pricing.yaml``, first readable file wins — the same
convention as the governance pack). Every rate comes from config, never
from code: no rate in the pack means the cost is unknown, never
fabricated.

The pack is declarative and versioned like the other policy packs::

    version: 1
    currency: USD          # D12: USD default, configurable per workspace
    models:
      anthropic:
        claude-opus-4-1:
          tokensInPerMillion: 15.0
          tokensOutPerMillion: 75.0
      "*":                 # vendor wildcard: rate by model id alone
        gpt-5:
          tokensInPerMillion: 1.25
          tokensOutPerMillion: 10.0

Parsing is fail-closed exactly like the FR-M12-01 governance pack: YAML
errors and schema violations come back as ``errors`` and a pack with any
error prices nothing — a malformed pack never invents a rate.

Absent-file behaviour (D43 uniformity rule, stated once in
``governance/bootstrap.py``): the sidecar bootstrap scaffolds the shipped
``pricing.yaml`` into ``<ws>/.meridian/policy/`` on workspace handshake;
only a loader invoked with no file anywhere yields the empty pack, and a
present-but-invalid pack fails closed naming the file, the violation,
and the remedy (fix the file, or delete it and restart to re-scaffold
the shipped default).

Zero model calls (FR-M36-07): table lookups and multiplication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from ..governance.bootstrap import FAIL_CLOSED_REMEDY

__all__ = ["PricingPack", "load_pricing_pack", "parse_pricing_pack"]

DEFAULT_CURRENCY = "USD"


@dataclass(frozen=True)
class ModelRate:
    """One vendor/model rate card: USD per million tokens, in and out."""

    vendor: str
    model: str
    tokens_in_per_million: float
    tokens_out_per_million: float


@dataclass
class PricingPack:
    """The parsed pricing pack. ``errors`` non-empty means fail-closed:
    ``price`` reports None for everything — a malformed pack never
    fabricates a rate."""

    version: int
    source: str
    currency: str = DEFAULT_CURRENCY
    rates: list[ModelRate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def fail_closed(self) -> bool:
        return bool(self.errors)

    def rate_for(self, vendor: str | None, model: str | None) -> ModelRate | None:
        """The exact vendor+model rate, falling back to the vendor
        wildcard ('*') entry for the model. No match -> None (unknown)."""
        if model:
            for rate in self.rates:
                if rate.model == model and rate.vendor == vendor:
                    return rate
            for rate in self.rates:
                if rate.model == model and rate.vendor == "*":
                    return rate
        return None

    def price(
        self,
        vendor: str | None,
        model: str | None,
        tokens_in: int,
        tokens_out: int,
    ) -> float | None:
        """USD cost for a token count, or None when the pack has no rate
        (or is fail-closed) — unknown, never fabricated."""
        rate = self.rate_for(vendor, model)
        if rate is None:
            return None
        cost = (
            tokens_in * rate.tokens_in_per_million
            + tokens_out * rate.tokens_out_per_million
        ) / 1_000_000.0
        return round(cost, 6)


def _rate_count(value: Any, where: str, errors: list[str]) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        errors.append(f"{where}: expected a number >= 0, got {value!r}")
        return None
    return float(value)


def parse_pricing_pack(text: str, source: str) -> PricingPack:
    """Parse and validate one pricing pack document. Never raises on
    content: every violation lands in ``errors`` and the pack prices
    nothing."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return PricingPack(
            version=0,
            source=source,
            errors=[f"{source}: not valid YAML: {error}", FAIL_CLOSED_REMEDY],
        )
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        return PricingPack(
            version=0,
            source=source,
            errors=[f"{source}: must be a mapping at the top level", FAIL_CLOSED_REMEDY],
        )

    errors: list[str] = []
    version = raw.get("version")
    if not (isinstance(version, int) and not isinstance(version, bool) and version >= 1):
        errors.append(f"version: expected an integer >= 1, got {version!r}")
        version = 0
    unknown = set(raw) - {"version", "currency", "models"}
    for name in sorted(unknown):
        errors.append(f"{name}: unknown top-level section")
    currency = raw.get("currency", DEFAULT_CURRENCY)
    if not isinstance(currency, str) or not currency.strip():
        errors.append(f"currency: expected a non-empty string, got {currency!r}")
        currency = DEFAULT_CURRENCY

    rates: list[ModelRate] = []
    models = raw.get("models", {})
    if not isinstance(models, Mapping):
        errors.append("models: expected a mapping of vendor -> model -> rates")
    else:
        for vendor, model_map in models.items():
            where = f"models.{vendor}"
            if not isinstance(vendor, str) or not vendor.strip():
                errors.append("models: vendor keys must be non-empty strings")
                continue
            if not isinstance(model_map, Mapping):
                errors.append(f"{where}: expected a mapping of model -> rates")
                continue
            for model, rate_map in model_map.items():
                mwhere = f"{where}.{model}"
                if not isinstance(model, str) or not model.strip():
                    errors.append(f"{where}: model keys must be non-empty strings")
                    continue
                if not isinstance(rate_map, Mapping):
                    errors.append(f"{mwhere}: expected a mapping with token rates")
                    continue
                unknown_keys = set(rate_map) - {"tokensInPerMillion", "tokensOutPerMillion"}
                for key in sorted(unknown_keys):
                    errors.append(f"{mwhere}: unknown key {key}")
                tokens_in = _rate_count(
                    rate_map.get("tokensInPerMillion"), f"{mwhere}.tokensInPerMillion", errors
                )
                tokens_out = _rate_count(
                    rate_map.get("tokensOutPerMillion"), f"{mwhere}.tokensOutPerMillion", errors
                )
                if tokens_in is None or tokens_out is None:
                    continue
                rates.append(
                    ModelRate(
                        vendor=vendor.strip(),
                        model=model.strip(),
                        tokens_in_per_million=tokens_in,
                        tokens_out_per_million=tokens_out,
                    )
                )
    if errors:
        return PricingPack(
            version=version,
            source=source,
            errors=[f"{source}: {e}" for e in errors] + [FAIL_CLOSED_REMEDY],
        )
    return PricingPack(
        version=version, source=source, currency=currency.strip(), rates=rates
    )


def load_pricing_pack(paths: Sequence[str | Path]) -> PricingPack:
    """First readable file wins (workspace override, then repository
    default). No readable file yields an empty pack: no rates, no errors —
    every cost lookup reports unknown, never an exception."""
    tried: list[str] = []
    for path in paths:
        candidate = Path(path)
        tried.append(str(candidate))
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        return parse_pricing_pack(text, str(candidate))
    return PricingPack(version=1, source="pricing-pack", rates=[])
