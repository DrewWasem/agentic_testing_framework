"""The ``evaluate`` convenience layer: one call, offline by default, returns a real Verdict.

Every test here runs on the mock — ``evaluate`` defaults to ``MockProvider``, so it makes no
network call and needs no API key, the same promise the rest of the suite keeps.
"""

from agentic_testing_framework import Verdict, evaluate
from agentic_testing_framework.providers.mock import MockProvider
from agentic_testing_framework.tribunal.checks import NonEmptyCheck, WordCountCheck


def test_evaluate_returns_passing_verdict_on_the_mock():
    verdict = evaluate("q", "hello world", "exp", criteria=["c1"])
    assert isinstance(verdict, Verdict)
    # The offline mock adjudicates a clean output as PASS.
    assert verdict.passed
    assert verdict.outcome.value == "pass"


def test_evaluate_default_path_makes_the_mocks_six_calls():
    # A custom provider lets us count the calls the default pipeline makes: reviewer (1) +
    # council (4 lenses) + orchestrator (1) = 6. This pins evaluate to the same shape the
    # CLI example run has, so it can't silently start spending more.
    provider = MockProvider()
    evaluate("q", "hello world", "exp", provider=provider)
    assert provider.call_count == 6


def test_evaluate_accepts_custom_checks():
    # A custom check list flows through build_pipeline's checks= seam.
    verdict = evaluate(
        "q", "hello world", "exp", checks=[NonEmptyCheck(), WordCountCheck(min_words=1)]
    )
    assert isinstance(verdict, Verdict)
    # The clerk ran exactly the checks we passed, so their findings are in the ledger.
    sources = {f.source for f in verdict.findings}
    assert "clerk:word_count" in sources


def test_evaluate_accepts_custom_lenses():
    # Overriding the council lenses changes how many reviewers deliberate: one lens means
    # reviewer (1) + council (1) + orchestrator (1) = 3 calls.
    provider = MockProvider()
    verdict = evaluate("q", "hello world", "exp", provider=provider, lenses=["accuracy"])
    assert isinstance(verdict, Verdict)
    assert provider.call_count == 3


def test_evaluate_makes_no_network_call(monkeypatch):
    # Belt and braces: forbid the live SDK path entirely, then prove evaluate still runs.
    import agentic_testing_framework.providers.anthropic as anthropic_mod

    def _boom(*args, **kwargs):
        raise AssertionError("evaluate must not construct a real provider")

    monkeypatch.setattr(anthropic_mod, "AnthropicProvider", _boom)
    verdict = evaluate("q", "hello world", "exp")
    assert isinstance(verdict, Verdict)
