"""The metric library: named LLM-judge lenses, offline, writing to the shared ledger.

Every test runs against ``MockProvider`` -- no API key, no network. Metrics are opt-in, so
the default example pipeline's six model calls are unchanged.
"""

import json

import pytest

from agentic_testing_framework import (
    Case,
    EvidenceLedger,
    GEval,
    MockProvider,
    Outcome,
    Severity,
    build_pipeline,
    get_metric,
    run_metrics,
)
from agentic_testing_framework.metrics.registry import METRICS


def _case() -> Case:
    return Case(
        input="Write a SQL query for total revenue per region in 2025.",
        output="SELECT region, SUM(amount) AS revenue FROM orders WHERE year=2025 GROUP BY region;",
        expectation="A correct, runnable SQL query answering the question.",
        criteria=["Groups by region", "Filters to 2025"],
    )


def test_every_registered_metric_runs_offline_and_writes_a_finding():
    for name, metric in METRICS.items():
        ledger = EvidenceLedger()
        finding = metric.evaluate(_case(), MockProvider(), ledger)
        # one finding, written to the ledger, sourced under metric:<name>
        assert len(ledger) == 1
        assert finding.source == f"metric:{name}"
        assert finding.id == f"metric:{name}#0"
        # a numeric normalized score lives in metadata, in 0..1
        score = finding.metadata["score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert finding.metadata["metric"] == name
        assert finding.metadata["raw_score"] is not None
        assert finding.metadata["scale"] == metric.scale
        # a non-empty quoted evidence span
        assert finding.evidence
        # passed and severity are consistent with the score/threshold
        assert finding.passed is (score >= metric.threshold)
        if finding.passed:
            assert finding.severity is Severity.INFO
        else:
            assert finding.severity in (Severity.MEDIUM, Severity.HIGH)


def test_g_eval_records_auto_derived_evaluation_steps():
    ledger = EvidenceLedger()
    finding = GEval().evaluate(_case(), MockProvider(), ledger)
    steps = finding.metadata["steps"]
    assert isinstance(steps, list)
    assert steps  # non-empty: G-Eval derived its rubric before scoring
    assert all(isinstance(s, str) and s for s in steps)


def test_inverse_metrics_score_clean_output_high():
    # hallucination/toxicity are inverse: a benign output should normalize near 1.0 (clean),
    # even though the model reports a LOW raw "amount of bad thing" score.
    for name in ("hallucination", "toxicity"):
        finding = get_metric(name).evaluate(_case(), MockProvider(), EvidenceLedger())
        assert finding.metadata["score"] == 1.0
        assert finding.metadata["raw_score"] == 1.0
        assert finding.passed is True


def test_inverse_metric_high_raw_score_fails_toxic_output():
    # The safety-critical direction: a TOXIC output (raw 5/5 "very toxic") MUST normalize to
    # 0.0 and FAIL. A wrong inversion would let toxic/hallucinated output pass as "good".
    scripted = json.dumps({"score": 5, "reasoning": "very toxic", "evidence": "the slur"})
    for name in ("toxicity", "hallucination"):
        finding = get_metric(name).evaluate(_case(), MockProvider([scripted]), EvidenceLedger())
        assert finding.metadata["raw_score"] == 5.0
        assert finding.metadata["score"] == 0.0, name
        assert finding.passed is False, name
        assert finding.severity is Severity.HIGH, name


def test_direct_metric_low_raw_score_fails():
    # Direct metric (g_eval): a worst-case raw 1/5 must normalize to 0.0 and FAIL.
    scripted = json.dumps({"score": 1, "reasoning": "does not meet expectation", "evidence": "x"})
    finding = GEval().evaluate(_case(), MockProvider([scripted]), EvidenceLedger())
    assert finding.metadata["raw_score"] == 1.0
    assert finding.metadata["score"] == 0.0
    assert finding.passed is False
    assert finding.severity is Severity.HIGH


def test_non_finite_score_fails_closed():
    # A NaN/inf score must NOT pass open (clamping would otherwise map it to the scale max).
    for bad in ("NaN", "inf", "-inf"):
        scripted = json.dumps({"score": bad, "reasoning": "r", "evidence": "e"})
        finding = GEval().evaluate(_case(), MockProvider([scripted]), EvidenceLedger())
        assert finding.metadata["score"] is None, bad
        assert finding.passed is False, bad


def test_run_metrics_aggregates_mean_of_per_metric_scores():
    names = ["g_eval", "faithfulness", "answer_relevancy", "hallucination", "toxicity"]
    report = run_metrics(_case(), MockProvider(), metrics=names)
    # the report's mean equals the mean of the numeric per-metric scores
    numeric = [s for s in report.scores.values() if s is not None]
    assert report.mean == pytest.approx(sum(numeric) / len(numeric))
    assert set(report.scores) == set(names)
    assert report.passed is True


def test_run_metrics_writes_one_finding_per_metric_into_the_ledger():
    ledger = EvidenceLedger()
    names = ["g_eval", "toxicity"]
    report = run_metrics(_case(), MockProvider(), metrics=names, ledger=ledger)
    assert len(ledger) == len(names)
    assert len(report.findings) == len(names)
    assert report.ledger is ledger
    assert {f.metadata["metric"] for f in report.findings} == set(names)


def test_run_metrics_aggregation_works_for_one_and_for_many():
    one = run_metrics(_case(), MockProvider(), metrics=["g_eval"])
    assert len(one.findings) == 1
    assert one.mean == one.scores["g_eval"]

    many = run_metrics(
        _case(),
        MockProvider(),
        metrics=["g_eval", "faithfulness", "answer_relevancy"],
    )
    assert len(many.findings) == 3
    assert many.mean == pytest.approx(sum(many.scores.values()) / 3)


def test_run_metrics_uses_a_fresh_ledger_when_none_given():
    report = run_metrics(_case(), MockProvider(), metrics=["g_eval"])
    assert isinstance(report.ledger, EvidenceLedger)
    assert len(report.ledger) == 1


def test_run_metrics_rejects_an_empty_metric_list():
    with pytest.raises(ValueError):
        run_metrics(_case(), MockProvider(), metrics=[])


def test_get_metric_raises_a_clear_error_on_unknown_name():
    with pytest.raises(KeyError) as excinfo:
        get_metric("definitely_not_a_metric")
    message = str(excinfo.value)
    assert "definitely_not_a_metric" in message
    # the error lists the valid names so the caller can fix the typo
    assert "g_eval" in message
    assert "toxicity" in message


def test_metric_tolerantly_parses_a_loose_string_score():
    # mirror _coerce_passed robustness: a string score, even spelled "4/5", still parses.
    scripted = json.dumps(
        {"score": "4/5", "reasoning": "mostly there", "evidence": "SELECT region"}
    )
    finding = GEval().evaluate(_case(), MockProvider([scripted]), EvidenceLedger())
    assert finding.metadata["raw_score"] == 4.0
    assert finding.metadata["score"] == pytest.approx(0.75)  # (4-1)/(5-1)
    assert finding.passed is True


def test_metric_handles_a_spelled_out_word_score():
    scripted = json.dumps({"score": "five", "reasoning": "great", "evidence": "x"})
    finding = GEval().evaluate(_case(), MockProvider([scripted]), EvidenceLedger())
    assert finding.metadata["raw_score"] == 5.0
    assert finding.metadata["score"] == 1.0


def test_metric_degrades_to_a_failing_finding_on_unparseable_output():
    # symmetry with the reviewer/council: junk in -> one failing finding, not a crash.
    finding = GEval().evaluate(
        _case(), MockProvider(["not json", "still not json"]), EvidenceLedger()
    )
    assert finding.passed is False
    assert finding.metadata["score"] is None
    assert "could not be parsed" in finding.message


def test_metric_with_no_numeric_score_fails_rather_than_inventing_one():
    scripted = json.dumps({"score": "n/a", "reasoning": "could not tell", "evidence": "e"})
    finding = GEval().evaluate(_case(), MockProvider([scripted]), EvidenceLedger())
    assert finding.metadata["score"] is None
    assert finding.passed is False


def test_default_example_pipeline_still_makes_exactly_six_llm_calls():
    # The whole point of opt-in metrics: they do NOT run in the default pipeline.
    pipeline = build_pipeline(MockProvider())
    verdict = pipeline.run_case(_case())
    assert verdict.outcome is Outcome.PASS
    assert verdict.total_llm_calls == 6  # reviewer 1 + council 4 + orchestrator 1
    # no metric finding leaked into the default run
    assert not [f for f in verdict.findings if f.source.startswith("metric:")]
