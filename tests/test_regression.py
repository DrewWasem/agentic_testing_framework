"""Golden-set regression: drift is measured on the verdict outcome, gated by a budget.

Everything runs offline through ``build_pipeline()`` (MockProvider). A golden whose
expectations match the mock has zero drift and passes; an injected wrong expectation is
reported as a flip and fails at a zero budget; ``update_baseline`` makes a failing set match
itself again; and the comparison is on the ``Outcome`` property, never the rationale prose.
"""

import json

from agentic_testing_framework import (
    Case,
    GoldenCase,
    GoldenSet,
    MockProvider,
    Outcome,
    build_pipeline,
    load_golden,
    run_regression,
    update_baseline,
)
from agentic_testing_framework.cli import main


def _matching_golden() -> list[GoldenCase]:
    # The offline mock rules PASS when no finding fails — these all pass with default checks.
    return [
        GoldenCase(
            "ok-1",
            Case(input="q1", expectation="e1", output="hello world", criteria=["c1"]),
            Outcome.PASS,
        ),
        GoldenCase(
            "ok-2",
            Case(input="q2", expectation="e2", output="another fine answer", criteria=["c2"]),
            Outcome.PASS,
        ),
    ]


def test_matching_golden_has_no_drift_and_passes():
    report = run_regression(_matching_golden(), build_pipeline(MockProvider()))
    assert report.flips == 0
    assert report.total == 2
    assert report.drift == 0.0
    assert report.passed is True
    assert all(r.status == "match" for r in report.results)


def test_wrong_expected_outcome_is_reported_as_a_flip_and_fails_at_zero_budget():
    golden = _matching_golden()
    # ok-2 actually passes offline; declaring it FAIL must surface as a flip.
    golden[1] = GoldenCase(golden[1].case_id, golden[1].case, Outcome.FAIL)
    report = run_regression(golden, build_pipeline(MockProvider()), max_drift=0.0)
    assert report.flips == 1
    assert report.passed is False
    flipped = report.flipped
    assert len(flipped) == 1
    assert flipped[0].case_id == "ok-2"
    assert flipped[0].expected is Outcome.FAIL
    assert flipped[0].actual is Outcome.PASS


def test_drift_within_budget_passes():
    golden = _matching_golden()
    golden[1] = GoldenCase(golden[1].case_id, golden[1].case, Outcome.FAIL)
    # 1 of 2 flipped = 0.5 drift; a 0.5 budget tolerates it.
    report = run_regression(golden, build_pipeline(MockProvider()), max_drift=0.5)
    assert report.drift == 0.5
    assert report.passed is True


def test_comparison_is_on_outcome_not_rationale_text():
    # Two providers whose verdicts agree on OUTCOME but differ in rationale wording must both
    # count as a match — the baseline is on the property, never the prose.
    golden = [
        GoldenCase("c", Case(input="q", expectation="e", output="x", criteria=["c1"]), Outcome.PASS)
    ]
    report_a = run_regression(golden, build_pipeline(MockProvider()))
    # A scripted orchestrator with a different rationale but the same PASS outcome.
    scripted = json.dumps(
        {"outcome": "pass", "rationale": "ENTIRELY DIFFERENT WORDING", "cited_findings": []}
    )
    report_b = run_regression(
        golden,
        build_pipeline(MockProvider(handler=lambda system, prompt: _route(system, scripted))),
    )
    assert report_a.passed is True
    assert report_b.passed is True  # rationale differs, outcome matches -> no flip


def _route(system: str, orchestrator_response: str) -> str:
    # Let the reviewer/council auto-respond; only override the orchestrator's ruling text.
    from agentic_testing_framework.core.roles import ROLE_ORCHESTRATOR, detect_role
    from agentic_testing_framework.providers.mock import _auto_response

    if detect_role(system) == ROLE_ORCHESTRATOR:
        return orchestrator_response
    return _auto_response(system, "")


def test_update_baseline_makes_a_failing_set_pass(tmp_path):
    path = tmp_path / "golden.json"
    # A baseline whose expectations are wrong (all FAIL though the mock passes).
    bad = [
        {
            "id": "x",
            "input": "q",
            "output": "x",
            "expectation": "e",
            "criteria": ["c1"],
            "expected": {"outcome": "fail"},
        }
    ]
    path.write_text(json.dumps(bad), encoding="utf-8")

    golden = load_golden(path)
    pipeline = build_pipeline(MockProvider())
    assert run_regression(golden, pipeline).passed is False  # fails before update

    update_baseline(str(path), pipeline, golden)
    reloaded = load_golden(path)
    assert reloaded[0].expected is Outcome.PASS  # rewritten to the actual outcome
    assert run_regression(reloaded, build_pipeline(MockProvider())).passed is True


def test_goldenset_load_save_roundtrip(tmp_path):
    path = tmp_path / "gs.json"
    GoldenSet(tuple(_matching_golden())).save(path)
    loaded = GoldenSet.load(path)
    assert len(loaded) == 2
    assert [gc.case_id for gc in loaded] == ["ok-1", "ok-2"]
    report = run_regression(loaded, build_pipeline(MockProvider()))
    assert report.passed is True


def test_load_golden_reads_the_example_baseline():
    golden = load_golden("examples/golden.json")
    assert {gc.case_id for gc in golden} == {"sql-revenue", "haiku-autumn", "list-primes"}
    # The shipped baseline matches the offline pipeline it documents.
    assert run_regression(golden, build_pipeline(MockProvider())).passed is True


def test_cli_regression_exits_zero_on_clean_baseline(capsys):
    assert main(["regression", "--golden", "examples/golden.json"]) == 0
    out = capsys.readouterr().out
    assert "drift=0.000" in out
    assert "PASS" in out


def test_cli_regression_exits_nonzero_on_drift(tmp_path, capsys):
    path = tmp_path / "golden.json"
    bad = [
        {
            "id": "x",
            "input": "q",
            "output": "x",
            "expectation": "e",
            "criteria": ["c1"],
            "expected": {"outcome": "fail"},
        }
    ]
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert main(["regression", "--golden", str(path)]) == 1
    out = capsys.readouterr().out
    assert "FLIP" in out
    assert "FAIL" in out


def test_cli_regression_update_baseline_exits_zero_and_then_passes(tmp_path, capsys):
    path = tmp_path / "golden.json"
    bad = [
        {
            "id": "x",
            "input": "q",
            "output": "x",
            "expectation": "e",
            "criteria": ["c1"],
            "expected": {"outcome": "fail"},
        }
    ]
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert main(["regression", "--golden", str(path), "--update-baseline"]) == 0
    # After the rewrite, a plain run is clean.
    assert main(["regression", "--golden", str(path)]) == 0


def test_cli_regression_missing_file_fails_cleanly(tmp_path, capsys):
    # A typo'd path must produce a clean error line + exit 2, never a traceback.
    code = main(["regression", "--golden", str(tmp_path / "nope.json")])
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_regression_malformed_json_fails_cleanly(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("this is not json {{{", encoding="utf-8")
    assert main(["regression", "--golden", str(path)]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_regression_unknown_outcome_fails_cleanly(tmp_path, capsys):
    path = tmp_path / "weird.json"
    path.write_text(
        json.dumps(
            [{"id": "x", "input": "q", "expectation": "e", "expected": {"outcome": "passs"}}]
        ),
        encoding="utf-8",
    )
    assert main(["regression", "--golden", str(path)]) == 2
    err = capsys.readouterr().err
    assert "error:" in err and "passs" in err


def test_load_golden_rejects_unknown_outcome(tmp_path):
    path = tmp_path / "weird.json"
    path.write_text(
        json.dumps(
            [{"id": "x", "input": "q", "expectation": "e", "expected": {"outcome": "nope"}}]
        ),
        encoding="utf-8",
    )
    try:
        load_golden(path)
        raised = False
    except ValueError:
        raised = True
    assert raised, "load_golden must reject an unknown outcome value"
