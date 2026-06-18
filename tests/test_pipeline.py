"""End-to-end pipeline: offline pass, stage costs, model tiering call counts."""

from agentic_testing_framework import Case, MockProvider, Outcome, build_pipeline


def test_full_pipeline_offline_pass():
    pipeline = build_pipeline(MockProvider())
    verdict = pipeline.run_case(
        Case(input="q", expectation="exp", output="hello world", criteria=["c1"])
    )
    assert verdict.outcome is Outcome.PASS
    assert verdict.gated is False
    stages = {cost.stage for cost in verdict.stage_costs}
    assert {"clerk", "reviewer", "council", "orchestrator"} <= stages
    # default council has 4 lenses: reviewer(1) + council(4) + orchestrator(1) = 6
    assert verdict.total_llm_calls == 6
    assert len(verdict.findings) >= 3  # at least the three clerk findings


def test_pipeline_clerk_stage_is_free():
    pipeline = build_pipeline(MockProvider())
    verdict = pipeline.run_case(Case(input="q", expectation="e", output="x"))
    clerk_cost = next(c for c in verdict.stage_costs if c.stage == "clerk")
    assert clerk_cost.llm_calls == 0


def test_run_suite():
    pipeline = build_pipeline()
    verdicts = pipeline.run_suite(
        [Case(input="a", expectation="e", output="x"), Case(input="b", expectation="e", output="y")]
    )
    assert len(verdicts) == 2
