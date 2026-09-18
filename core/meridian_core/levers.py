"""FR-M26-04 (audit TASK-310): configurable cost levers on the model-call
path — prompt caching, context compaction, and tool-result summarisation —
with their savings recorded per call and reportable per story and in
aggregate.

All three levers are deterministic and zero-model-call: they shape what a
call WOULD cost; the recording of savings rides the ledger entries the
router already writes.

- **Prompt caching** — the canonical prefix of a call's prompt (config-
  defined depth, default 4 KiB) is hashed; a repeat within the TTL reuses
  the cached suffix tokens: cache hits record `cachedTokens` as savings.
- **Context compaction** — when a call's prompt exceeds the configured
  budget, the oldest tool results are dropped first (they are the least
  decision-relevant and their removal is marked, never silent) until the
  prompt fits.
- **Tool-result summarisation** — results above the cap are replaced by a
  capped extract carrying :data:`TRUNCATION_MARKER`, exactly the shape the
  tool layer already guarantees (FR-M9-04), applied to model context here.

Savings accounting is honest: `LeverReport` counts tokens the levers
removed from what the call would otherwise have sent. No invented
provider-side discounts.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from meridian_core.tools.surface import TRUNCATION_MARKER

DEFAULT_PREFIX_BYTES = 4096
DEFAULT_TTL_S = 900.0
DEFAULT_CONTEXT_BUDGET_BYTES = 64_000
DEFAULT_RESULT_CAP_BYTES = 8_000


@dataclass(frozen=True)
class LeverConfig:
    """Config-pack shape for the three levers. Defaults are on; a pack may
    disable any lever (``enabled=False``) and the lever is a pass-through —
    a disabled lever never silently shapes a call."""

    prompt_caching: bool = True
    cache_prefix_bytes: int = DEFAULT_PREFIX_BYTES
    cache_ttl_s: float = DEFAULT_TTL_S
    context_compaction: bool = True
    context_budget_bytes: int = DEFAULT_CONTEXT_BUDGET_BYTES
    tool_result_summarisation: bool = True
    result_cap_bytes: int = DEFAULT_RESULT_CAP_BYTES


@dataclass(frozen=True)
class LeverSavings:
    """What the levers removed from one call."""

    cached_tokens: int = 0
    compacted_bytes: int = 0
    summarised_bytes: int = 0

    @property
    def total_bytes(self) -> int:
        return self.compacted_bytes + self.summarised_bytes

    def to_dict(self) -> dict[str, int]:
        return {
            "cachedTokens": self.cached_tokens,
            "compactedBytes": self.compacted_bytes,
            "summarisedBytes": self.summarised_bytes,
        }


class _CacheEntry:
    __slots__ = ("suffix_tokens", "expires")

    def __init__(self, suffix_tokens: int, expires: float) -> None:
        self.suffix_tokens = suffix_tokens
        self.expires = expires


class CostLeverSet:
    """The three levers, applied in order: cache → compact → summarise."""

    def __init__(
        self,
        config: LeverConfig | None = None,
        *,
        now: Any = time.monotonic,
    ) -> None:
        self._config = config or LeverConfig()
        self._now = now
        self._cache: dict[str, _CacheEntry] = {}

    @property
    def config(self) -> LeverConfig:
        return self._config

    def apply(
        self,
        *,
        prompt: str,
        story_id: str,
        why_llm: str,
        tokens_estimate: Any = None,
    ) -> tuple[str, LeverSavings]:
        """Shape one model call. Returns the (possibly reduced) prompt and
        the savings the levers achieved. ``why_llm`` is recorded so cache
        hits carry the same governance label as fresh calls."""
        savings = LeverSavings()
        shaped = prompt

        if self._config.prompt_caching:
            shaped, cached = self._apply_cache(shaped, story_id)
            savings = LeverSavings(
                cached_tokens=cached,
                compacted_bytes=savings.compacted_bytes,
                summarised_bytes=savings.summarised_bytes,
            )

        if self._config.context_compaction:
            shaped, removed = self._apply_compaction(shaped)
            savings = LeverSavings(
                cached_tokens=savings.cached_tokens,
                compacted_bytes=removed,
                summarised_bytes=savings.summarised_bytes,
            )

        if self._config.tool_result_summarisation:
            shaped, removed = self._apply_summarisation(shaped)
            savings = LeverSavings(
                cached_tokens=savings.cached_tokens,
                compacted_bytes=savings.compacted_bytes,
                summarised_bytes=removed,
            )

        return shaped, savings

    # -- prompt caching ----------------------------------------------------

    def _apply_cache(self, prompt: str, story_id: str) -> tuple[str, int]:
        """Prefix-hash caching: a repeat of the same prefix within the TTL
        is charged only for the suffix. Estimation rule, stated because a
        hidden estimator is a fabricated number: one token ≈ four bytes of
        prompt; the cache stores the suffix length on first sight."""
        prefix = prompt[: self._config.cache_prefix_bytes]
        suffix = prompt[self._config.cache_prefix_bytes:]
        key = hashlib.sha256((story_id + "\n" + prefix).encode("utf-8")).hexdigest()
        entry = self._cache.get(key)
        now = self._now()
        if entry is not None and entry.expires > now:
            cached_tokens = max(1, len(prefix) // 4)
            return suffix, cached_tokens
        self._cache[key] = _CacheEntry(
            suffix_tokens=len(suffix), expires=now + self._config.cache_ttl_s
        )
        return prompt, 0

    # -- context compaction ---------------------------------------------------

    TOOL_RESULT_MARKERS = ("tool result:", "tool_result:", "<tool", "[tool")

    def _apply_compaction(self, prompt: str) -> tuple[str, int]:
        """Oldest tool results drop first until the prompt fits the budget.
        Removal is marked — compaction is disclosed in the shaped prompt."""
        budget = self._config.context_budget_bytes
        if len(prompt.encode("utf-8")) <= budget:
            return prompt, 0
        lines = prompt.split("\n")
        removed_bytes = 0
        kept: list[str] = []
        for line in lines:
            is_tool = any(m in line.lower() for m in self.TOOL_RESULT_MARKERS)
            if (
                is_tool
                and len("\n".join(kept + lines[lines.index(line):]).encode("utf-8"))
                > budget
            ):
                removed_bytes += len(line.encode("utf-8")) + 1
                continue
            kept.append(line)
        shaped = "\n".join(kept)
        if removed_bytes:
            shaped = (
                f"[context compacted: {removed_bytes} bytes of oldest tool"
                " results dropped first (FR-M26-04)]\n" + shaped
            )
        return shaped, removed_bytes

    # -- tool-result summarisation ----------------------------------------------

    def _apply_summarisation(self, prompt: str) -> tuple[str, int]:
        """Oversized tool-result blocks are replaced by a capped extract
        carrying the explicit truncation marker (FR-M9-04's shape)."""
        cap = self._config.result_cap_bytes
        out: list[str] = []
        removed = 0
        for line in prompt.split("\n"):
            encoded = line.encode("utf-8")
            is_tool = any(m in line.lower() for m in self.TOOL_RESULT_MARKERS)
            if is_tool and len(encoded) > cap:
                kept = encoded[:cap].decode("utf-8", "ignore")
                out.append(kept + TRUNCATION_MARKER)
                removed += len(encoded) - cap
            else:
                out.append(line)
        return "\n".join(out), removed


@dataclass
class LeverReport:
    """Aggregate savings, per story and overall. fed by Router."""

    by_story: dict[str, LeverSavings] = field(default_factory=dict)

    def record(self, story_id: str, savings: LeverSavings) -> None:
        current = self.by_story.get(story_id, LeverSavings())
        self.by_story[story_id] = LeverSavings(
            cached_tokens=current.cached_tokens + savings.cached_tokens,
            compacted_bytes=current.compacted_bytes + savings.compacted_bytes,
            summarised_bytes=current.summarised_bytes + savings.summarised_bytes,
        )

    def for_story(self, story_id: str) -> Mapping[str, int]:
        savings = self.by_story.get(story_id, LeverSavings())
        return savings.to_dict()

    def aggregate(self) -> Mapping[str, int]:
        total = LeverSavings()
        for savings in self.by_story.values():
            total = LeverSavings(
                cached_tokens=total.cached_tokens + savings.cached_tokens,
                compacted_bytes=total.compacted_bytes + savings.compacted_bytes,
                summarised_bytes=total.summarised_bytes + savings.summarised_bytes,
            )
        return total.to_dict()


def config_from_pack(raw: Mapping[str, Any] | None) -> LeverConfig:
    """Parse a governance pack's ``cost_levers`` section; absent or partial
    config yields defaults (all levers on)."""
    raw = raw or {}
    return LeverConfig(
        prompt_caching=bool(raw.get("promptCaching", True)),
        cache_prefix_bytes=int(raw.get("cachePrefixBytes", DEFAULT_PREFIX_BYTES)),
        cache_ttl_s=float(raw.get("cacheTtlSeconds", DEFAULT_TTL_S)),
        context_compaction=bool(raw.get("contextCompaction", True)),
        context_budget_bytes=int(
            raw.get("contextBudgetBytes", DEFAULT_CONTEXT_BUDGET_BYTES)
        ),
        tool_result_summarisation=bool(raw.get("toolResultSummarisation", True)),
        result_cap_bytes=int(raw.get("resultCapBytes", DEFAULT_RESULT_CAP_BYTES)),
    )


def savings_to_ledger_detail(savings: LeverSavings) -> str:
    """The lever evidence rides the existing model_call entry's detail."""
    return json.dumps({"levers": savings.to_dict()}, sort_keys=True)
