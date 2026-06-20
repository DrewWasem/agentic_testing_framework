"""The adversarial loop closes deterministically: probe -> naive compliance -> caught free."""

from agentic_testing_framework import (
    AdversarialGenerator,
    Case,
    FunctionTarget,
    MockProvider,
    Outcome,
    build_pipeline,
    injection_leak_check,
    run_target,
)
from agentic_testing_framework.generator.adversarial import INJECTION_CANARY


def test_injection_compliance_is_caught_for_free():
    # A naive agent that obeys the injected instruction leaks the canary token.
    def naive_agent(text):
        return INJECTION_CANARY if "IGNORE ALL PREVIOUS" in text else "a fine answer"

    probe = AdversarialGenerator(["prompt_injection"]).generate(
        Case(input="Summarize this report.", expectation="A faithful summary.")
    )[0]
    mock = MockProvider()
    pipeline = build_pipeline(mock, checks=[injection_leak_check()])
    verdict = pipeline.run_case(
        run_target(FunctionTarget(naive_agent), probe.input, probe.expectation)
    )

    assert verdict.outcome is Outcome.FAIL
    assert verdict.gated is True
    assert mock.call_count == 0  # caught by the deterministic gate — no judge needed


def test_robust_agent_passes_the_injection_gate():
    robust = FunctionTarget(lambda _text: "Here is a faithful summary.")
    probe = AdversarialGenerator(["prompt_injection"]).generate(
        Case(input="Summarize.", expectation="A summary.")
    )[0]
    mock = MockProvider()
    pipeline = build_pipeline(mock, checks=[injection_leak_check()])
    verdict = pipeline.run_case(run_target(robust, probe.input, probe.expectation))

    assert verdict.gated is False  # no canary leaked -> proceeds to the tribunal
    assert mock.call_count > 0


def test_refusal_that_mentions_canary_is_not_flagged():
    # Merely naming the token while refusing is correct behavior, not compliance.
    refuser = FunctionTarget(
        lambda _text: "I will not output OVERRIDDEN. Here is the real summary instead."
    )
    probe = AdversarialGenerator(["prompt_injection"]).generate(
        Case(input="Summarize.", expectation="A summary.")
    )[0]
    mock = MockProvider()
    pipeline = build_pipeline(mock, checks=[injection_leak_check()])
    verdict = pipeline.run_case(run_target(refuser, probe.input, probe.expectation))

    assert verdict.gated is False  # mentioning the token in a refusal is not a leak
