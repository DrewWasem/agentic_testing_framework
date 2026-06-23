"""Advisory (out-of-scope) findings: structured, separable, never verdict-driving.

An advisory finding is a TRUE observation the stated expectation/criteria did not require
(e.g. "this palindrome check is case-sensitive"). It must be recorded in the ledger and
surfaced in a dedicated report section, but it must never count toward the pass/fail verdict
and carries ``passed=None`` by convention. These tests pin that contract end to end, all
offline against the mock.
"""

import json

from agentic_testing_framework import (
    PROMPTS,
    Case,
    Finding,
    MockProvider,
    Outcome,
    Severity,
    Verdict,
    build_pipeline,
    render_html,
)
from agentic_testing_framework.cli import _print_verdict
from agentic_testing_framework.tribunal._judging import parse_findings


def test_parse_findings_reads_advisory_true_and_forces_passed_none():
    # A model marks a beyond-spec issue advisory: it is neither a pass nor a fail of a
    # stated criterion, so ``passed`` is forced to None regardless of what was supplied.
    items = [
        {
            "criterion": "c1",
            "passed": False,
            "severity": "medium",
            "message": "case-sensitive comparison is beyond the spec",
            "evidence": "lower()",
            "advisory": True,
        }
    ]
    findings = parse_findings(items, "council:adversarial")
    assert len(findings) == 1
    assert findings[0].advisory is True
    assert findings[0].passed is None  # forced, even though "passed": False was supplied


def test_parse_findings_absent_advisory_key_defaults_false():
    # The advisory key is OPTIONAL: existing responses with no key parse unchanged.
    items = [{"criterion": "c1", "passed": True, "severity": "info", "message": "ok"}]
    findings = parse_findings(items, "reviewer")
    assert findings[0].advisory is False
    assert findings[0].passed is True  # untouched when not advisory


def test_parse_findings_is_tolerant_of_loose_advisory_values():
    # Mirror _coerce_passed's tolerance: strings/ints/loose truthy values are accepted.
    truthy = parse_findings(
        [{"message": "m", "advisory": "yes"}, {"message": "m", "advisory": 1}], "reviewer"
    )
    assert all(f.advisory is True for f in truthy)
    assert all(f.passed is None for f in truthy)
    # A JSON string "false" must stay False (not flip on via a naive bool()).
    falsey = parse_findings(
        [{"message": "m", "advisory": "false"}, {"message": "m", "advisory": 0}], "reviewer"
    )
    assert all(f.advisory is False for f in falsey)


def test_directly_constructed_advisory_finding_behaves_and_renders():
    finding = Finding(
        source="council:adversarial",
        severity=Severity.LOW,
        message="dedup crashes on unhashable items (beyond spec)",
        evidence="set(items)",
        passed=None,
        advisory=True,
        id="council:adversarial#0",
    )
    assert finding.advisory is True
    assert finding.passed is None
    verdict = Verdict(
        outcome=Outcome.PASS,
        rationale="meets the stated spec",
        findings=(finding,),
    )
    html = render_html(verdict)
    # It renders (no crash) and appears under the advisory section header.
    assert "Also noted — advisory (beyond the stated spec)" in html
    assert "dedup crashes on unhashable items" in html


def test_html_separates_advisory_from_main_ledger():
    in_scope = Finding(
        source="reviewer",
        severity=Severity.HIGH,
        message="MAIN-LEDGER-FAILURE-TEXT",
        passed=False,
        id="reviewer#0",
    )
    advisory = Finding(
        source="council:adversarial",
        severity=Severity.LOW,
        message="ADVISORY-BEYOND-SPEC-TEXT",
        passed=None,
        advisory=True,
        id="council:adversarial#0",
    )
    verdict = Verdict(
        outcome=Outcome.FAIL,
        rationale="failed a stated criterion",
        findings=(in_scope, advisory),
    )
    html = render_html(verdict)
    header = "Also noted — advisory (beyond the stated spec)"
    assert header in html
    # The advisory text appears AFTER the advisory header; the in-scope failure appears
    # BEFORE it (i.e. in the main ledger), proving the two are in separate sections.
    head_at = html.index(header)
    assert html.index("ADVISORY-BEYOND-SPEC-TEXT") > head_at
    assert html.index("MAIN-LEDGER-FAILURE-TEXT") < head_at


def test_html_omits_advisory_section_when_none_present():
    finding = Finding(
        source="reviewer", severity=Severity.INFO, message="ok", passed=True, id="reviewer#0"
    )
    verdict = Verdict(outcome=Outcome.PASS, rationale="r", findings=(finding,))
    html = render_html(verdict)
    assert "Also noted — advisory" not in html


def test_cli_print_verdict_shows_advisory_section_when_present(capsys):
    in_scope = Finding(
        source="reviewer",
        severity=Severity.INFO,
        message="in-scope note",
        passed=True,
        id="reviewer#0",
    )
    advisory = Finding(
        source="council:adversarial",
        severity=Severity.LOW,
        message="beyond-spec advisory note",
        passed=None,
        advisory=True,
        id="council:adversarial#0",
    )
    verdict = Verdict(outcome=Outcome.PASS, rationale="r", findings=(in_scope, advisory))
    _print_verdict(verdict)
    out = capsys.readouterr().out
    assert "Also noted — advisory (beyond the stated spec):" in out
    assert "beyond-spec advisory note" in out
    # The in-scope finding prints under the normal ledger, not the advisory section.
    ledger_at = out.index("Evidence ledger:")
    advisory_at = out.index("Also noted — advisory")
    assert out.index("in-scope note") > ledger_at
    assert out.index("in-scope note") < advisory_at


def test_cli_print_verdict_omits_advisory_section_when_absent(capsys):
    finding = Finding(
        source="reviewer", severity=Severity.INFO, message="ok", passed=True, id="reviewer#0"
    )
    _print_verdict(Verdict(outcome=Outcome.PASS, rationale="r", findings=(finding,)))
    out = capsys.readouterr().out
    assert "Also noted — advisory" not in out


def test_backward_compat_mock_pipeline_still_six_calls():
    # The offline mock needs NO advisory changes: a default run still completes and the
    # six-call cost is unchanged.
    provider = MockProvider()
    verdict = build_pipeline(provider).run_case(
        Case(input="q", expectation="exp", output="hello world", criteria=["c1"])
    )
    assert verdict.outcome is Outcome.PASS
    assert verdict.total_llm_calls == 6


def test_backward_compat_existing_council_json_parses_without_advisory():
    # Reviewer/council JSON with no advisory key (the mock's exact shape) parses with
    # advisory=False and the supplied passed value untouched.
    items = [
        {
            "criterion": "c1",
            "passed": True,
            "severity": "info",
            "message": "looks right",
            "evidence": "e",
        }
    ]
    findings = parse_findings(items, "council:accuracy", extra_meta={"lens": "accuracy"})
    assert findings[0].advisory is False
    assert findings[0].passed is True


def test_advisory_does_not_flip_offline_verdict_to_fail():
    # An advisory council finding (passed=None) must not trip the mock orchestrator, which
    # fails only when a finding actually FAILs. Script one lens to emit an advisory.
    advisory_lens = json.dumps(
        {
            "findings": [
                {
                    "criterion": "c1",
                    "passed": None,
                    "severity": "low",
                    "message": "case-sensitive, beyond the spec",
                    "evidence": "e",
                    "advisory": True,
                }
            ],
            "summary": "one beyond-spec note",
        }
    )
    # reviewer(1) + council(4: one scripted advisory, three auto-empty) + orchestrator(1).
    provider = MockProvider(
        [
            json.dumps({"findings": [], "summary": "ok"}),  # reviewer
            advisory_lens,  # council:accuracy
        ]
    )
    verdict = build_pipeline(provider).run_case(
        Case(input="q", expectation="exp", output="hello world", criteria=["c1"])
    )
    assert verdict.outcome is Outcome.PASS  # the advisory did NOT cause a FAIL
    advisory_findings = [f for f in verdict.findings if f.advisory]
    assert len(advisory_findings) == 1
    assert advisory_findings[0].passed is None


def test_verdict_records_bumped_prompt_versions():
    # The version stamp reflects the bumped reviewer/council/orchestrator prompts; read the
    # expected numbers from the registry rather than hardcoding them.
    verdict = build_pipeline(MockProvider()).run_case(
        Case(input="q", expectation="exp", output="hello world", criteria=["c1"])
    )
    assert verdict.prompt_versions == {
        "reviewer": PROMPTS["reviewer"].version,
        "council": PROMPTS["council"].version,
        "orchestrator": PROMPTS["orchestrator"].version,
    }
    # And those are the post-bump versions this change introduced.
    assert PROMPTS["reviewer"].version == 2
    assert PROMPTS["council"].version == 3
    assert PROMPTS["orchestrator"].version == 3
