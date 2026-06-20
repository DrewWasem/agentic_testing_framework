"""The Clerk's hard gate: a failed gate decides the case with zero model calls."""

from agentic_testing_framework import Case, MockProvider, Outcome, WordCountCheck, build_pipeline


def test_hard_gate_short_circuits_with_zero_model_calls():
    mock = MockProvider()
    pipeline = build_pipeline(mock, checks=[WordCountCheck(max_words=5, gate=True)])
    case = Case(
        input="x",
        expectation="keep it short",
        output="one two three four five six seven eight nine ten",
    )
    verdict = pipeline.run_case(case)
    assert verdict.outcome is Outcome.FAIL
    assert verdict.gated is True
    assert verdict.total_llm_calls == 0
    assert mock.call_count == 0  # the whole point: a failed gate costs $0
    assert verdict.cited_findings  # the gate finding is cited


def test_passing_gate_proceeds_to_the_model():
    mock = MockProvider()
    pipeline = build_pipeline(mock, checks=[WordCountCheck(max_words=50, gate=True)])
    verdict = pipeline.run_case(Case(input="x", expectation="short", output="a few words here"))
    assert verdict.gated is False
    assert mock.call_count > 0
