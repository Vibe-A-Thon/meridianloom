"""Predictable pricing pack (FR-M39-04; F1 Workstream F task 29).

Per-vendor/model token rates from config (policy/pricing.yaml), so
recorded tokens x rate = cost. All rates from config, never hard-coded:
a model with no rate prices as unknown, never fabricated. D12: USD
default, configurable via the currency key.
"""

from __future__ import annotations

from meridian_core.metrics import load_pricing_pack, parse_pricing_pack

PACK = """
version: 1
currency: USD
models:
  anthropic:
    claude-opus-4-1:
      tokensInPerMillion: 15.0
      tokensOutPerMillion: 75.0
  "*":
    gpt-5:
      tokensInPerMillion: 1.25
      tokensOutPerMillion: 10.0
"""


class TestParse:
    def test_valid_pack(self):
        pack = parse_pricing_pack(PACK, "test")
        assert not pack.fail_closed
        assert pack.version == 1
        assert pack.currency == "USD"
        assert len(pack.rates) == 2

    def test_d12_usd_default_when_currency_absent(self):
        pack = parse_pricing_pack(
            "version: 1\nmodels:\n  v:\n    m:\n"
            "      tokensInPerMillion: 1\n      tokensOutPerMillion: 2\n",
            "test",
        )
        assert not pack.fail_closed
        assert pack.currency == "USD"

    def test_currency_configurable(self):
        pack = parse_pricing_pack(
            "version: 1\ncurrency: EUR\nmodels: {}\n", "test"
        )
        assert pack.currency == "EUR"

    def test_unknown_top_level_section_rejected(self):
        pack = parse_pricing_pack(
            "version: 1\nsurprises:\n  x: 1\nmodels: {}\n", "test"
        )
        assert pack.fail_closed

    def test_bad_version_rejected(self):
        pack = parse_pricing_pack("version: zero\nmodels: {}\n", "test")
        assert pack.fail_closed

    def test_negative_rate_rejected(self):
        pack = parse_pricing_pack(
            "version: 1\nmodels:\n  v:\n    m:\n"
            "      tokensInPerMillion: -1\n      tokensOutPerMillion: 2\n",
            "test",
        )
        assert pack.fail_closed

    def test_missing_rate_rejected(self):
        pack = parse_pricing_pack(
            "version: 1\nmodels:\n  v:\n    m:\n      tokensInPerMillion: 1\n",
            "test",
        )
        assert pack.fail_closed

    def test_not_yaml_fails_closed(self):
        pack = parse_pricing_pack("{unclosed", "test")
        assert pack.fail_closed


class TestPricing:
    def test_tokens_times_rate_is_cost(self):
        pack = parse_pricing_pack(PACK, "test")
        # 1M in at 15/M + 0.5M out at 75/M = 15 + 37.5 = 52.5
        assert pack.price("anthropic", "claude-opus-4-1", 1_000_000, 500_000) == 52.5

    def test_wildcard_vendor_matches_any_vendor_tag(self):
        pack = parse_pricing_pack(PACK, "test")
        # gpt-5 has no exact vendor entry; the "*" vendor row prices it
        # no matter which vendor tag the ledger carried.
        assert pack.price("openai", "gpt-5", 1_000_000, 0) == 1.25
        assert pack.price("any-vendor", "gpt-5", 1_000_000, 0) == 1.25

    def test_unknown_model_is_unknown_never_fabricated(self):
        pack = parse_pricing_pack(PACK, "test")
        assert pack.price("anthropic", "claude-9", 1_000_000, 1_000_000) is None
        assert pack.price("nope", None, 1_000_000, 0) is None

    def test_fail_closed_pack_prices_nothing(self):
        pack = parse_pricing_pack("version: bad\n", "test")
        assert pack.fail_closed
        assert pack.price("anthropic", "claude-opus-4-1", 1_000_000, 0) is None

    def test_repository_pack_loads(self):
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        pack = load_pricing_pack([repo_root / "policy" / "pricing.yaml"])
        assert not pack.fail_closed
        assert pack.currency == "USD"
        # The pack makes Governor/Orchestra's own models free by design
        # (Flight Recorder: no usage-based cost) and prices the vendors.
        assert pack.price("meridian", "meridian-governor", 1_000_000, 1_000_000) == 0.0
        assert pack.price("anthropic", "claude-sonnet-4-5", 1_000_000, 1_000_000) == 18.0

    def test_no_file_is_empty_not_error(self, tmp_path):
        pack = load_pricing_pack([tmp_path / "missing.yaml"])
        assert not pack.fail_closed
        assert pack.rates == []
        assert pack.price("v", "m", 1, 1) is None

    def test_first_readable_wins(self, tmp_path):
        override = tmp_path / "pricing.yaml"
        override.write_text(
            "version: 1\nmodels:\n  v:\n    m:\n"
            "      tokensInPerMillion: 99\n      tokensOutPerMillion: 99\n",
            encoding="utf-8",
        )
        pack = load_pricing_pack([override, tmp_path / "missing.yaml"])
        assert pack.price("v", "m", 1_000_000, 0) == 99.0
