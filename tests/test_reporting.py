"""Reporting: HTML ledger render, JUnit XML shape, CLI flags, and the gate exit code.

Everything runs offline: a real verdict comes from ``build_pipeline(MockProvider())``,
and ``Verdict``/``Finding`` are also constructed directly to exercise HTML-escaping and
the non-PASS failure path without depending on the mock's routing.
"""

from xml.dom.minidom import parseString

from agentic_testing_framework import (
    Case,
    Finding,
    MockProvider,
    Outcome,
    Severity,
    Verdict,
    build_pipeline,
    render_html,
    render_junit,
)
from agentic_testing_framework.cli import _exit_code, main


def _real_verdict() -> Verdict:
    pipeline = build_pipeline(MockProvider())
    return pipeline.run_case(
        Case(input="q", expectation="exp", output="hello world", criteria=["c1"])
    )


def test_render_html_contains_ids_rationale_and_severity():
    verdict = _real_verdict()
    html = render_html(verdict)
    # Every finding id is present in the ledger render.
    for finding in verdict.findings:
        assert finding.id in html
    # The orchestrator's rationale is shown.
    assert verdict.rationale in html
    # Severity labels appear.
    assert "info" in html
    # It is a complete, self-contained document with inline styles and no external assets.
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html
    assert "http://" not in html and "https://" not in html


def test_render_html_includes_case_when_given():
    case = Case(input="the-input", expectation="the-expectation", output="the-output")
    verdict = build_pipeline(MockProvider()).run_case(case)
    html = render_html(verdict, case=case)
    assert "the-input" in html
    assert "the-expectation" in html


def test_render_html_escapes_injected_markup():
    finding = Finding(
        source="reviewer",
        severity=Severity.HIGH,
        message="danger <script>alert(1)</script>",
        evidence="<img src=x onerror=alert(2)>",
        passed=False,
        id="reviewer#0",
    )
    verdict = Verdict(
        outcome=Outcome.FAIL,
        rationale="bad <script>steal()</script> output",
        cited_findings=("reviewer#0",),
        findings=(finding,),
    )
    html = render_html(verdict)
    # The escaped form appears...
    assert "&lt;script&gt;" in html
    # ...and the raw, executable tag does not.
    assert "<script>" not in html
    assert "<img src=x" not in html


def test_render_html_renders_stage_cost_table():
    verdict = _real_verdict()
    html = render_html(verdict)
    assert "Stage costs" in html
    # Field names from StageCost are used as column headers; this keeps working when
    # later work appends fields, so just assert the ones present today.
    assert "stage" in html
    assert "llm_calls" in html


def test_render_junit_parses_and_has_testsuite_and_testcase():
    verdict = _real_verdict()
    xml = render_junit([("example", verdict)])
    doc = parseString(xml)  # raises if not well-formed
    suites = doc.getElementsByTagName("testsuite")
    assert len(suites) == 1
    assert suites[0].getAttribute("tests") == "1"
    cases = doc.getElementsByTagName("testcase")
    assert len(cases) == 1
    assert cases[0].getAttribute("name") == "example"


def test_render_junit_pass_has_no_failure():
    verdict = Verdict(outcome=Outcome.PASS, rationale="all good")
    doc = parseString(render_junit([("ok", verdict)]))
    assert len(doc.getElementsByTagName("failure")) == 0
    assert doc.getElementsByTagName("testsuite")[0].getAttribute("failures") == "0"


def test_render_junit_nonpass_emits_failure_with_rationale_and_citations():
    verdict = Verdict(
        outcome=Outcome.FAIL,
        rationale="output did not group by region",
        cited_findings=("reviewer#0", "council:accuracy#1"),
    )
    doc = parseString(render_junit([("bad", verdict)]))
    suite = doc.getElementsByTagName("testsuite")[0]
    assert suite.getAttribute("failures") == "1"
    failures = doc.getElementsByTagName("failure")
    assert len(failures) == 1
    assert failures[0].getAttribute("message") == "output did not group by region"
    body = failures[0].firstChild.data
    assert "reviewer#0" in body
    assert "council:accuracy#1" in body


def test_render_junit_escapes_attributes_and_text():
    verdict = Verdict(outcome=Outcome.FAIL, rationale='bad <thing> & "quote"')
    xml = render_junit([('name <with> & "marks"', verdict)])
    parseString(xml)  # well-formed despite the metacharacters
    assert "<thing>" not in xml
    assert "&lt;thing&gt;" in xml or "&lt;thing>" in xml


def test_cli_writes_html_and_junit(tmp_path):
    html_path = tmp_path / "report.html"
    xml_path = tmp_path / "results.xml"
    code = main(["run", "--example", "--html", str(html_path), "--junit", str(xml_path)])
    assert code == 0
    assert html_path.exists() and html_path.stat().st_size > 0
    assert xml_path.exists() and xml_path.stat().st_size > 0
    parseString(xml_path.read_text())  # the written JUnit is valid XML
    assert "<!DOCTYPE html>" in html_path.read_text()


def test_cli_gate_passes_on_pass(tmp_path):
    # The offline example PASSes, so --gate must not change the exit code.
    assert main(["run", "--example", "--gate"]) == 0


def test_exit_code_pass_with_gate_is_zero():
    assert _exit_code(Verdict(outcome=Outcome.PASS, rationale="r"), True) == 0


def test_exit_code_fail_with_gate_is_one():
    assert _exit_code(Verdict(outcome=Outcome.FAIL, rationale="r"), True) == 1


def test_exit_code_fail_without_gate_is_zero():
    assert _exit_code(Verdict(outcome=Outcome.FAIL, rationale="r"), False) == 0


def test_render_html_escapes_every_dynamic_field():
    # Inject a distinct, unique markup marker into EVERY model/user-derived field, then
    # prove each one is neutralized. This pins the headline safety property so dropping
    # escape() from any single field (source, criterion, id, case fields, title, …) fails.
    case = Case(
        input="<x-input>",
        expectation="<x-exp>",
        output="<x-output>",
        criteria=["<x-criterion-item>"],
    )
    finding = Finding(
        source="<x-source>",
        severity=Severity.HIGH,
        message="<x-message>",
        evidence="<x-evidence>",
        criterion="<x-finding-criterion>",
        passed=False,
        id="<x-id>",
    )
    verdict = Verdict(
        outcome=Outcome.FAIL,
        rationale="<x-rationale>",
        cited_findings=("<x-cited>",),
        findings=(finding,),
    )
    html = render_html(verdict, case=case, title="<x-title>")
    for marker in (
        "<x-input>",
        "<x-exp>",
        "<x-output>",
        "<x-criterion-item>",
        "<x-source>",
        "<x-message>",
        "<x-evidence>",
        "<x-finding-criterion>",
        "<x-id>",
        "<x-rationale>",
        "<x-cited>",
        "<x-title>",
    ):
        escaped = marker.replace("<", "&lt;").replace(">", "&gt;")
        assert marker not in html, f"unescaped {marker!r} leaked into the report"
        assert escaped in html, f"expected escaped {escaped!r} in the report"


def test_cli_write_failure_returns_nonzero_without_traceback(tmp_path):
    # Parent directory does not exist -> OSError on open. Must be handled, not raised.
    bad = tmp_path / "missing-dir" / "report.html"
    assert main(["run", "--example", "--html", str(bad)]) == 1
