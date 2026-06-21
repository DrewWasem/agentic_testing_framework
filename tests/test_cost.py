"""Per-stage latency + estimated cost: honest accounting, $0 for gate/cache/unpriced."""

from agentic_testing_framework import (
    CachingProvider,
    Case,
    CountingProvider,
    MockProvider,
    build_pipeline,
)
from agentic_testing_framework.core.models import DEFAULT_MODELS, ModelPrice, Tier, price_for


class _SpyProvider:
    name = "spy"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        return "X" * 40  # known-length response for the token-estimate check


def test_price_for_known_and_unknown_models():
    # Pin the ACTUAL list prices so a stale-price regression (e.g. Opus at the old $15/$75)
    # fails loudly — a positivity-only check would green-light a 3x-wrong price.
    assert price_for(DEFAULT_MODELS[Tier.CHEAP]) == ModelPrice(1.0, 5.0)  # claude-haiku-4-5
    assert price_for(DEFAULT_MODELS[Tier.MID]) == ModelPrice(3.0, 15.0)  # claude-sonnet-4-6
    assert price_for(DEFAULT_MODELS[Tier.FRONTIER]) == ModelPrice(5.0, 25.0)  # claude-opus-4-8
    assert price_for("mock") is None
    assert price_for("not-a-real-model") is None
    assert price_for(None) is None


def test_unpriced_model_costs_zero_but_records_latency():
    spy = _SpyProvider()
    meter = CountingProvider(spy)  # model_id defaults to None → unpriced → free
    meter.complete("system", "prompt")
    assert meter.cost_usd == 0.0
    assert meter.latency_s >= 0.0


def test_priced_model_cost_matches_token_estimate_formula():
    spy = _SpyProvider()
    cheap = DEFAULT_MODELS[Tier.CHEAP]
    meter = CountingProvider(spy, model_id=cheap)
    system, prompt = "system text", "prompt text"
    response = meter.complete(system, prompt)
    price = price_for(cheap)
    assert price is not None
    in_tok = (len(system) + len(prompt)) / 4
    out_tok = len(response) / 4
    expected = in_tok / 1e6 * price.input_per_mtok + out_tok / 1e6 * price.output_per_mtok
    assert expected > 0
    assert abs(meter.cost_usd - expected) < 1e-12


def test_cache_hit_contributes_zero_cost(tmp_path):
    spy = _SpyProvider()
    cache = CachingProvider(spy, tmp_path)
    cheap = DEFAULT_MODELS[Tier.CHEAP]
    meter = CountingProvider(cache, model_id=cheap)
    # First call is a real miss → priced.
    meter.complete("s", "p")
    after_miss = meter.cost_usd
    assert after_miss > 0
    # Second identical call is a cache hit → adds $0, though it still counts as a call.
    meter.complete("s", "p")
    assert meter.calls == 2
    assert meter.cost_usd == after_miss  # unchanged: the hit was free
    assert spy.calls == 1


def test_reset_zeros_latency_and_cost():
    meter = CountingProvider(_SpyProvider(), model_id=DEFAULT_MODELS[Tier.CHEAP])
    meter.complete("s", "p")
    meter.reset()
    assert meter.calls == 0
    assert meter.latency_s == 0.0
    assert meter.cost_usd == 0.0


def test_verdict_totals_sum_stage_costs_offline():
    verdict = build_pipeline(MockProvider()).run_case(
        Case(input="q", expectation="exp", output="hello world", criteria=["c1"])
    )
    # The totals are exactly the sum of the per-stage fields (one source of truth).
    assert verdict.total_cost_usd == sum(c.cost_usd for c in verdict.stage_costs)
    assert verdict.total_latency_s == sum(c.latency_s for c in verdict.stage_costs)
    # build_pipeline prices each stage at its INTENDED tier (cheap reviewer/council,
    # frontier orchestrator), so the estimate is > 0 at default-tier list prices even
    # though the mock runs every stage offline — it is an estimate, not a bill.
    assert verdict.total_cost_usd > 0.0
    assert verdict.total_latency_s >= 0.0
    # The clerk is free, and the orchestrator (frontier) is the priciest single stage.
    by_stage = {c.stage: c for c in verdict.stage_costs}
    assert by_stage["clerk"].cost_usd == 0.0
    # The cost-by-construction call count stays pinned at 6 for the default example.
    assert verdict.total_llm_calls == 6


def test_hard_gated_case_costs_zero():
    # A required-pattern check that the output cannot satisfy, set as a hard gate.
    from agentic_testing_framework import RequiredPatternCheck

    gate = RequiredPatternCheck(["WILL-NOT-APPEAR"], gate=True)
    pipeline = build_pipeline(MockProvider(), checks=[gate])
    verdict = pipeline.run_case(Case(input="q", expectation="e", output="nothing here"))
    assert verdict.gated is True
    assert verdict.total_cost_usd == 0.0
    assert verdict.total_latency_s == 0.0
    assert verdict.total_llm_calls == 0
    # Only the clerk stage is recorded on a short-circuit.
    assert [c.stage for c in verdict.stage_costs] == ["clerk"]
