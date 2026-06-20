"""The adaptive loop: failures in one round drive more cases of that category next round."""

from agentic_testing_framework import (
    AdaptiveLoop,
    AdversarialGenerator,
    Case,
    FunctionTarget,
    WordCountCheck,
    build_pipeline,
)


def test_adaptive_loop_targets_failing_category():
    # An agent that always over-produces — it will fail a tight word-count gate every time.
    target = FunctionTarget(lambda _text: "word " * 80)
    pipeline = build_pipeline(checks=[WordCountCheck(max_words=20, gate=True)])
    seeds = AdversarialGenerator(["scope_creep"]).generate(
        Case(input="Do X.", expectation="Stay scoped.")
    )

    report = AdaptiveLoop(pipeline, target=target).run(seeds, rounds=2)

    assert report.rounds == 2
    assert report.cases_run >= 2
    # round 1 (seed) + round 2 (regenerated in the failing category) both failed
    assert report.failures_by_category.get("scope_creep", 0) >= 2


def test_adaptive_loop_handles_empty_seeds():
    report = AdaptiveLoop(build_pipeline()).run([], rounds=2)
    assert report.cases_run == 0
    assert report.rounds == 0
