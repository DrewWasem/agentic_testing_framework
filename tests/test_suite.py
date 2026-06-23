"""The suite report and the ``atf eval`` command — multi-case runs as one browsable artifact.

Everything runs offline: real verdicts come from ``build_pipeline(MockProvider())``, and the
HTML is parsed with ``html.parser`` (the renderer emits HTML5 void tags, so it is validated by
a non-erroring feed plus substring assertions, the same way ``render_html`` is). No API key,
no network.
"""

from html.parser import HTMLParser

import pytest

from agentic_testing_framework import (
    Case,
    MockProvider,
    NonEmptyCheck,
    Outcome,
    Verdict,
    build_pipeline,
    render_suite_html,
)
from agentic_testing_framework import cli as cli_mod


class _StrictHTMLParser(HTMLParser):
    """Raise on a malformed-markup error instead of swallowing it, so a feed = a validity check."""

    def error(self, message: str) -> None:  # pragma: no cover - only fires on broken HTML
        raise ValueError(message)


def _assert_parses(html: str) -> None:
    _StrictHTMLParser().feed(html)


def _suite_results() -> list[tuple[str, Verdict]]:
    pipeline = build_pipeline(MockProvider())
    return [
        ("sql-case", pipeline.run_case(Case(input="q1", expectation="e1", output="hello world"))),
        ("math-case", pipeline.run_case(Case(input="q2", expectation="e2", output="4"))),
    ]


def test_render_suite_html_is_self_contained_and_parses():
    html = render_suite_html(_suite_results())
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html
    # Self-contained: no external assets are referenced.
    assert "http://" not in html and "https://" not in html
    _assert_parses(html)


def test_render_suite_html_shows_summary_counts():
    html = render_suite_html(_suite_results())
    # Two cases, both PASS through the offline mock: the summary header reflects the tally.
    assert "2" in html
    assert "total" in html
    assert "pass" in html


def test_render_suite_html_lists_every_case_and_a_section_each():
    results = _suite_results()
    html = render_suite_html(results)
    for name, _ in results:
        assert name in html
    # One <section class='case-block'> per result — the per-case detail blocks below the table.
    assert html.count("class='case-block'") == len(results)


def test_render_suite_html_table_links_to_each_section():
    html = render_suite_html(_suite_results())
    # Each table row anchor-links to a section id that exists in the document.
    assert "href='#case-sql-case'" in html
    assert "id='case-sql-case'" in html


def test_render_suite_html_dedupes_repeated_case_names():
    pipeline = build_pipeline(MockProvider())
    v = pipeline.run_case(Case(input="q", expectation="e", output="x"))
    html = render_suite_html([("dup", v), ("dup", v)])
    # Two cases share a name; both still get a distinct, resolvable anchor (no collision).
    assert "id='case-dup'" in html
    assert "id='case-dup-1'" in html


def test_render_suite_html_escapes_injected_markup():
    pipeline = build_pipeline(MockProvider())
    v = pipeline.run_case(Case(input="q", expectation="e", output="x"))
    html = render_suite_html([("<script>alert(1)</script>", v)])
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_render_suite_html_renders_a_failed_case_badge():
    fail = Verdict(outcome=Outcome.FAIL, rationale="it failed")
    html = render_suite_html([("bad", fail)])
    assert "badge-fail" in html
    assert "it failed" in html


def test_render_suite_html_empty_is_still_valid():
    html = render_suite_html([])
    assert html.startswith("<!DOCTYPE html>")
    _assert_parses(html)
    assert "No cases were run." in html


# --- the `atf eval` command -------------------------------------------------------------


def _write_cases(tmp_path, payload: object) -> str:
    import json

    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload))
    return str(path)


def test_eval_runs_and_prints_per_case_summary(tmp_path, capsys):
    cases = _write_cases(
        tmp_path,
        [
            {"input": "q1", "output": "hello world", "expectation": "e1", "id": "first"},
            {"input": "q2", "output": "4", "expectation": "e2", "name": "second"},
        ],
    )
    assert cli_mod.main(["eval", "--cases", cases]) == 0
    out = capsys.readouterr().out
    assert "Suite:" in out
    assert "first" in out and "second" in out
    assert "PASS" in out


def test_eval_names_unlabeled_cases_by_position(tmp_path, capsys):
    cases = _write_cases(tmp_path, [{"input": "q", "output": "x", "expectation": "e"}])
    assert cli_mod.main(["eval", "--cases", cases]) == 0
    assert "case-0" in capsys.readouterr().out


def test_eval_writes_suite_html_with_all_case_names(tmp_path, capsys):
    cases = _write_cases(
        tmp_path,
        [
            {"input": "q1", "output": "x", "expectation": "e1", "id": "alpha"},
            {"input": "q2", "output": "y", "expectation": "e2", "id": "beta"},
        ],
    )
    html_path = tmp_path / "suite.html"
    assert cli_mod.main(["eval", "--cases", cases, "--html", str(html_path)]) == 0
    capsys.readouterr()
    body = html_path.read_text()
    assert "<!DOCTYPE html>" in body
    assert "alpha" in body and "beta" in body


def test_eval_open_calls_opener_with_written_html(tmp_path, monkeypatch, capsys):
    cases = _write_cases(tmp_path, [{"input": "q", "output": "x", "expectation": "e"}])
    html_path = tmp_path / "suite.html"
    opened: list[str] = []
    monkeypatch.setattr(cli_mod, "_open", lambda url: opened.append(url))
    assert cli_mod.main(["eval", "--cases", cases, "--html", str(html_path), "--open"]) == 0
    capsys.readouterr()
    assert html_path.exists()
    assert len(opened) == 1
    assert str(html_path) in opened[0]


def test_eval_open_without_html_errors(tmp_path, capsys):
    cases = _write_cases(tmp_path, [{"input": "q", "output": "x", "expectation": "e"}])
    with pytest.raises(SystemExit) as exc:
        cli_mod.main(["eval", "--cases", cases, "--open"])
    assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_eval_gate_returns_one_when_a_case_fails(tmp_path, monkeypatch, capsys):
    # Force a gating non-empty check into the pipeline eval builds, then feed an empty-output
    # case: it gate-FAILs while the non-empty case PASSes — so --gate must exit 1.
    original = cli_mod.build_pipeline

    def gating_pipeline(provider=None, **kwargs):
        kwargs["checks"] = [NonEmptyCheck(gate=True)]
        return original(provider, **kwargs)

    monkeypatch.setattr(cli_mod, "build_pipeline", gating_pipeline)
    cases = _write_cases(
        tmp_path,
        [
            {"input": "q1", "output": "hello world", "expectation": "e1", "id": "ok"},
            {"input": "q2", "output": "", "expectation": "e2", "id": "empty"},
        ],
    )
    code = cli_mod.main(["eval", "--cases", cases, "--gate"])
    assert code == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "PASS" in out


def test_eval_gate_returns_zero_when_all_pass(tmp_path, capsys):
    cases = _write_cases(
        tmp_path,
        [
            {"input": "q1", "output": "hello world", "expectation": "e1"},
            {"input": "q2", "output": "the capital is Paris", "expectation": "e2"},
        ],
    )
    assert cli_mod.main(["eval", "--cases", cases, "--gate"]) == 0
    capsys.readouterr()


def test_eval_empty_cases_file_is_a_clean_error(tmp_path, capsys):
    # An empty cases array must NOT silently pass --gate (any() of [] is False) — it's an error.
    cases = _write_cases(tmp_path, [])
    code = cli_mod.main(["eval", "--cases", cases, "--gate"])
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_eval_missing_cases_file_is_labelled_cases_not_case(tmp_path, capsys):
    code = cli_mod.main(["eval", "--cases", str(tmp_path / "nope.json")])
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err and "cases file" in err  # labelled for the right command


def test_render_suite_html_escapes_finding_and_rationale():
    # Lock the escaping guarantee on the content the suite actually renders (not just the name).
    from agentic_testing_framework import Finding, Severity

    f = Finding(
        source="reviewer",
        severity=Severity.HIGH,
        message="<script>alert(1)</script>",
        evidence="<img src=x onerror=y>",
        passed=False,
    )
    v = Verdict(outcome=Outcome.FAIL, rationale="bad <b>markup</b> here", findings=(f,))
    html = render_suite_html([("evil", v)])
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)" not in html
    assert "<img src=x" not in html
    assert "<b>markup</b>" not in html  # rationale is escaped too


def test_eval_missing_cases_file_is_clean_error(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    code = cli_mod.main(["eval", "--cases", str(missing)])
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "Traceback" not in err


def test_eval_non_array_cases_file_is_clean_error(tmp_path, capsys):
    cases = _write_cases(tmp_path, {"input": "q", "output": "x", "expectation": "e"})
    code = cli_mod.main(["eval", "--cases", cases])
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err and "array" in err
    assert "Traceback" not in err


def test_eval_malformed_json_cases_file_is_clean_error(tmp_path, capsys):
    path = tmp_path / "cases.json"
    path.write_text("not json [[[")
    code = cli_mod.main(["eval", "--cases", str(path)])
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "Traceback" not in err


def test_eval_wrong_type_element_is_clean_error(tmp_path, capsys):
    # A non-string 'output' in one element must NOT crash a downstream check with a traceback.
    cases = _write_cases(
        tmp_path,
        [{"input": "q", "expectation": "e", "output": {"not": "a string"}}],
    )
    code = cli_mod.main(["eval", "--cases", cases])
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err and "output" in err
    assert "Traceback" not in err


def test_eval_runs_the_bundled_example_cases(capsys):
    # The committed examples/cases.json must work out of the box and exit 0.
    code = cli_mod.main(["eval", "--cases", "examples/cases.json"])
    assert code == 0
    assert "Suite:" in capsys.readouterr().out
