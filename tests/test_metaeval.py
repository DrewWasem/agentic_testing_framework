"""Meta-evaluation: prove the judge against human gold labels, fully offline (mock).

Every test here runs against ``MockProvider`` -- no API key, no network. The real-judge path
(``ClaudeCLIProvider``, ``--judge claude-cli``) is reachable from the CLI but is never
exercised by a test. Covered: the stdlib agreement math (kappa on perfect/total-disagreement/
a hand-computed 2x2, raw agreement, fail-class precision/recall), dataset load/save and the
unknown-gold ValueError, the single-judge baseline offline, the runner over a tiny labeled
set, the gaming probe, the ``metaeval`` CLI, and proof the default ``atf run`` is unchanged.
"""

import json

import pytest

from agentic_testing_framework import (
    Case,
    LabeledCase,
    MetaEvalReport,
    MockProvider,
    Outcome,
    build_pipeline,
    cohens_kappa,
    confusion_matrix,
    gaming_pipeline,
    hollow_case,
    is_gamed,
    load_labeled,
    precision_recall,
    raw_agreement,
    render_markdown,
    run_metaeval,
    save_labeled,
    single_judge,
)
from agentic_testing_framework.cli import main

P = Outcome.PASS
F = Outcome.FAIL


# --- agreement math -------------------------------------------------------------------


def test_kappa_perfect_agreement_is_one():
    pairs = [(P, P), (F, F), (P, P), (F, F)]
    assert cohens_kappa(pairs) == pytest.approx(1.0)
    assert raw_agreement(pairs) == pytest.approx(1.0)


def test_kappa_total_disagreement_is_negative_or_zero():
    # Every prediction is the opposite of gold -> worse than chance -> kappa <= 0.
    pairs = [(P, F), (F, P), (P, F), (F, P)]
    assert cohens_kappa(pairs) <= 0.0
    assert raw_agreement(pairs) == pytest.approx(0.0)


def test_kappa_on_a_hand_computed_2x2():
    # Confusion: (fail,fail)=5, (pass,fail)=1, (fail,pass)=2, (pass,pass)=2; n=10.
    # p_o = (5+2)/10 = 0.7. Marginals gold(fail=7,pass=3), pred(fail=6,pass=4).
    # p_e = 0.7*0.6 + 0.3*0.4 = 0.42 + 0.12 = 0.54. kappa = (0.7-0.54)/(1-0.54) = 0.347826...
    pairs = [(F, F)] * 5 + [(P, F)] * 1 + [(F, P)] * 2 + [(P, P)] * 2
    assert cohens_kappa(pairs) == pytest.approx(0.16 / 0.46, abs=1e-6)


def test_kappa_degenerate_single_label_returns_one_or_zero():
    # Both raters used only PASS -> chance agreement is total (1 - p_e == 0). Agreeing
    # everywhere -> 1.0; the all-disagree single-label case can't occur, so 1.0 here.
    assert cohens_kappa([(P, P), (P, P)]) == pytest.approx(1.0)


def test_raw_agreement_on_a_known_matrix():
    pairs = [(P, P), (P, F), (F, F), (F, F)]  # 3 of 4 match
    assert raw_agreement(pairs) == pytest.approx(0.75)


def test_precision_recall_on_a_known_matrix():
    # fail is positive. TP=2 (fail,fail), FP=1 (pass,fail), FN=1 (fail,pass), TN=1 (pass,pass).
    pairs = [(F, F), (F, F), (P, F), (F, P), (P, P)]
    precision, recall, f1 = precision_recall(pairs, Outcome.FAIL)
    assert precision == pytest.approx(2 / 3)  # 2 / (2+1)
    assert recall == pytest.approx(2 / 3)  # 2 / (2+1)
    assert f1 == pytest.approx(2 / 3)


def test_precision_recall_no_predicted_positives_is_zero():
    pairs = [(F, P), (P, P)]  # judge never predicts fail
    precision, recall, f1 = precision_recall(pairs, Outcome.FAIL)
    assert (precision, recall, f1) == (0.0, 0.0, 0.0)


def test_confusion_matrix_is_dense_over_four_cells():
    matrix = confusion_matrix([(F, F), (P, P)])
    assert set(matrix) == {(P, P), (P, F), (F, P), (F, F)}
    assert matrix[(F, F)] == 1 and matrix[(P, P)] == 1
    assert matrix[(P, F)] == 0 and matrix[(F, P)] == 0


def test_empty_pairs_do_not_divide_by_zero():
    assert raw_agreement([]) == 0.0
    assert cohens_kappa([]) == 0.0
    assert precision_recall([], Outcome.FAIL) == (0.0, 0.0, 0.0)


# --- dataset --------------------------------------------------------------------------


def test_dataset_load_save_roundtrip(tmp_path):
    labeled = [
        LabeledCase("a", Case(input="q1", expectation="e1", output="o1", criteria=["c1"]), P),
        LabeledCase("b", Case(input="q2", expectation="e2", output="o2"), F),
    ]
    path = tmp_path / "labeled.json"
    save_labeled(path, labeled)
    loaded = load_labeled(path)
    assert [lc.case_id for lc in loaded] == ["a", "b"]
    assert [lc.gold for lc in loaded] == [P, F]
    assert loaded[0].case.criteria == ("c1",)
    # The gold id is mirrored into metadata so it survives a pipeline round-trip.
    assert loaded[0].case.metadata["labeled_id"] == "a"


def test_dataset_unknown_gold_raises_valueerror(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps([{"id": "x", "input": "q", "expectation": "e", "gold": "maybe"}]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_labeled(path)


def test_dataset_missing_gold_raises_valueerror(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"id": "x", "input": "q", "expectation": "e"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_labeled(path)


def test_load_the_shipped_labeled_dataset():
    labeled = load_labeled("examples/metaeval/labeled.json")
    assert len(labeled) >= 24
    # Every gold label is binary -- meta-eval scores a 2x2, never 'inconclusive'.
    assert all(lc.gold in (P, F) for lc in labeled)
    assert len({lc.case_id for lc in labeled}) == len(labeled)  # ids are unique


# --- single-judge baseline ------------------------------------------------------------


def test_single_judge_returns_pass_or_fail_offline():
    case = Case(input="q", expectation="e", output="a plausible answer")
    outcome = single_judge(case, MockProvider())
    assert outcome in (P, F)
    assert outcome is P  # the lenient offline baseline passes non-empty output


def test_single_judge_fails_closed_on_empty_output():
    case = Case(input="q", expectation="e", output="")
    assert single_judge(case, MockProvider()) is F


def test_single_judge_fails_closed_on_unparseable():
    case = Case(input="q", expectation="e", output="x")
    assert single_judge(case, MockProvider(["not json", "still not json"])) is F


def test_single_judge_honors_scripted_verdict():
    case = Case(input="q", expectation="e", output="x")
    fail = json.dumps({"verdict": "fail", "reason": "wrong question"})
    assert single_judge(case, MockProvider([fail])) is F


# --- runner ---------------------------------------------------------------------------


def _tiny_labeled() -> list[LabeledCase]:
    return [
        LabeledCase(
            "g1", Case(input="q1", expectation="e1", output="hello world", criteria=["c"]), P
        ),
        LabeledCase(
            "g2", Case(input="q2", expectation="e2", output="another answer", criteria=["c"]), P
        ),
        LabeledCase("b1", Case(input="q3", expectation="e3", output=""), F),
    ]


def test_run_metaeval_populates_both_judges_and_one_row_per_case():
    labeled = _tiny_labeled()
    report = run_metaeval(
        labeled, atf_pipeline=build_pipeline(MockProvider()), baseline_provider=MockProvider()
    )
    assert isinstance(report, MetaEvalReport)
    assert report.size == len(labeled)
    assert len(report.rows) == len({lc.case_id for lc in labeled})
    # Both judges' bundles are populated (a real float for each metric).
    for judge in (report.atf, report.baseline):
        assert judge.total == len(labeled)
        assert 0.0 <= judge.raw_agreement <= 1.0
        assert -1.0 <= judge.cohens_kappa <= 1.0
        assert 0.0 <= judge.fail_recall <= 1.0


def test_run_metaeval_inconclusive_maps_to_fail():
    # An orchestrator that can't parse -> INCONCLUSIVE -> mapped to FAIL by the runner.
    case = Case(input="q", expectation="e", output="x", criteria=["c"])
    labeled = [LabeledCase("c", case, F)]

    def route(system, prompt):
        from agentic_testing_framework.core.roles import ROLE_ORCHESTRATOR, detect_role
        from agentic_testing_framework.providers.mock import _auto_response

        if detect_role(system) == ROLE_ORCHESTRATOR:
            return "not json at all"
        return _auto_response(system, prompt)

    pipeline = build_pipeline(MockProvider(handler=route))
    report = run_metaeval(labeled, atf_pipeline=pipeline, baseline_provider=MockProvider())
    # gold is FAIL and the inconclusive verdict mapped to FAIL -> ATF agreed.
    assert report.rows[0].atf is F
    assert report.rows[0].atf_correct is True


def test_render_markdown_contains_both_judges_and_per_case_verdicts():
    report = run_metaeval(
        _tiny_labeled(),
        atf_pipeline=build_pipeline(MockProvider()),
        baseline_provider=MockProvider(),
    )
    md = render_markdown(report)
    assert "ATF tribunal" in md
    assert "Single-judge baseline" in md
    assert "Cohen's kappa" in md
    # Per-case rows name each labeled id and an honest bottom-line verdict.
    for row in report.rows:
        assert row.case_id in md
    assert "ATF agreed with" in md


# --- gaming probe ---------------------------------------------------------------------


def test_hollow_output_does_not_pass_atf_offline():
    # Form-over-substance output is caught by the deterministic substance checks, offline.
    pipeline = gaming_pipeline(MockProvider())
    assert is_gamed(pipeline) is False
    verdict = pipeline.run_case(hollow_case())
    assert verdict.outcome is not Outcome.PASS


def test_gaming_probe_accepts_a_custom_case():
    # A genuinely-good SQL answer through the same substance-checking pipeline is NOT gamed
    # (it passes legitimately, so is_gamed -- "fooled into PASS by hollow output" -- is the
    # PASS check; here we assert the probe runs and the real answer passes).
    good = Case(
        input="Write a SQL query for total revenue per region in 2025.",
        output=(
            "SELECT region, SUM(amount) AS revenue FROM orders WHERE year = 2025 GROUP BY region;"
        ),
        expectation="A correct SQL query.",
        criteria=["Contains an actual SQL SELECT statement"],
    )
    pipeline = gaming_pipeline(MockProvider())
    assert pipeline.run_case(good).outcome is Outcome.PASS


# --- CLI ------------------------------------------------------------------------------


def test_cli_metaeval_runs_offline_and_writes_a_report(tmp_path, capsys):
    dataset = tmp_path / "labeled.json"
    save_labeled(str(dataset), _tiny_labeled())
    out = tmp_path / "RESULTS.md"
    code = main(["metaeval", "--dataset", str(dataset), "--out", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "Meta-evaluation over 3" in printed
    assert "VERDICT: ATF agreed with" in printed
    # The report file was written and carries the comparison.
    text = out.read_text(encoding="utf-8")
    assert "ATF tribunal" in text and "Single-judge baseline" in text


def test_cli_metaeval_runs_on_the_shipped_dataset(capsys):
    code = main(["metaeval", "--dataset", "examples/metaeval/labeled.json"])
    assert code == 0
    assert "Meta-evaluation over" in capsys.readouterr().out


def test_cli_metaeval_missing_dataset_fails_cleanly(tmp_path, capsys):
    code = main(["metaeval", "--dataset", str(tmp_path / "nope.json")])
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_metaeval_judge_flag_defaults_to_mock(tmp_path):
    # --judge defaults to mock; an explicit mock is identical and stays offline.
    dataset = tmp_path / "labeled.json"
    save_labeled(str(dataset), _tiny_labeled())
    assert main(["metaeval", "--dataset", str(dataset), "--judge", "mock"]) == 0


# --- the default run is unchanged -----------------------------------------------------


def test_default_atf_run_is_unchanged_six_calls_mock():
    # The headline invariant: adding metaeval must not change the example's cost.
    verdict = build_pipeline(MockProvider()).run_case(
        Case(input="q", expectation="exp", output="hello world", criteria=["c1"])
    )
    assert verdict.outcome is Outcome.PASS
    assert verdict.total_llm_calls == 6


def test_cli_run_example_default_judge_is_offline(capsys):
    assert main(["run", "--example"]) == 0
    assert "VERDICT:" in capsys.readouterr().out
