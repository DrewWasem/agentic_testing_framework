"""The atf CLI: version, the offline example run, and evaluating an arbitrary case."""

import json

import pytest

from agentic_testing_framework import (
    Finding,
    Outcome,
    Severity,
    Verdict,
    __version__,
    cli,
)
from agentic_testing_framework.cli import _c, _print_verdict, main


def test_cli_version(capsys):
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_cli_run_example(capsys):
    assert main(["run", "--example"]) == 0
    out = capsys.readouterr().out
    assert "VERDICT:" in out
    assert "Evidence ledger:" in out


def test_cli_run_inline_case(capsys):
    code = main(
        [
            "run",
            "--input",
            "q",
            "--output",
            "hello world",
            "--expectation",
            "exp",
            "--criteria",
            "c1",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "VERDICT:" in out
    assert "Evidence ledger:" in out


def test_cli_run_case_file(tmp_path, capsys):
    case_file = tmp_path / "case.json"
    case_file.write_text(
        json.dumps(
            {
                "input": "Write SQL for revenue per region",
                "output": "SELECT region, SUM(amount) FROM orders GROUP BY region;",
                "expectation": "Correct SQL grouping by region",
                "criteria": ["Groups by region"],
            }
        )
    )
    assert main(["run", "--case-file", str(case_file)]) == 0
    assert "VERDICT:" in capsys.readouterr().out


def test_cli_run_missing_case_file_is_clean_error(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    code = main(["run", "--case-file", str(missing)])
    assert code == 2  # non-zero, not a crash
    err = capsys.readouterr().err
    assert err.startswith("error:") or "\nerror:" in err
    assert "Traceback" not in err


def test_cli_run_malformed_case_file_is_clean_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{{")
    code = main(["run", "--case-file", str(bad)])
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "Traceback" not in err


def test_cli_run_inline_missing_output_errors_cleanly(capsys):
    # An inline case with no --output is incomplete: argparse error (exit 2), not a crash.
    with pytest.raises(SystemExit) as exc:
        main(["run", "--input", "q", "--expectation", "exp"])
    assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_run_open_calls_opener_with_written_html(tmp_path, monkeypatch, capsys):
    html_path = tmp_path / "report.html"
    opened: list[str] = []
    monkeypatch.setattr(cli, "_open", lambda url: opened.append(url))
    assert main(["run", "--example", "--html", str(html_path), "--open"]) == 0
    capsys.readouterr()
    assert html_path.exists()
    # The opener was handed the path we wrote (wrapped as a file:// URL).
    assert len(opened) == 1
    assert str(html_path) in opened[0]


def test_cli_run_without_open_does_not_call_opener(tmp_path, monkeypatch, capsys):
    html_path = tmp_path / "report.html"
    opened: list[str] = []
    monkeypatch.setattr(cli, "_open", lambda url: opened.append(url))
    assert main(["run", "--example", "--html", str(html_path)]) == 0
    capsys.readouterr()
    assert opened == []  # no --open -> the browser is never touched


def test_cli_run_open_without_html_errors(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["run", "--example", "--open"])
    assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_run_case_file_non_string_output_is_clean_error(tmp_path, capsys):
    # A non-string 'output' must NOT crash a downstream check with a traceback.
    bad = tmp_path / "case.json"
    bad.write_text(json.dumps({"input": "q", "expectation": "e", "output": {"not": "a string"}}))
    code = main(["run", "--case-file", str(bad)])
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err and "output" in err


def test_cli_run_case_file_non_string_input_is_clean_error(tmp_path, capsys):
    bad = tmp_path / "case.json"
    bad.write_text(json.dumps({"input": 123, "expectation": "e", "output": "x"}))
    assert main(["run", "--case-file", str(bad)]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_run_case_file_criteria_not_a_list_is_clean_error(tmp_path, capsys):
    bad = tmp_path / "case.json"
    bad.write_text(
        json.dumps({"input": "q", "expectation": "e", "output": "x", "criteria": "oops"})
    )
    code = main(["run", "--case-file", str(bad)])
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err and "criteria" in err


def test_cli_run_case_file_null_output_is_valid(tmp_path, capsys):
    # An omitted/null 'output' is a legitimate "empty result" case — it must run, not error.
    case = tmp_path / "case.json"
    case.write_text(json.dumps({"input": "q", "expectation": "e", "output": None}))
    assert main(["run", "--case-file", str(case)]) == 0


# --- the colour helper and the reworked verdict printer ---------------------------------


def test_c_wraps_in_ansi_when_on():
    wrapped = _c("hi", "32", on=True)
    assert wrapped == "\033[32mhi\033[0m"


def test_c_is_plain_when_off():
    # Off -> the text is returned verbatim, with no escape codes at all.
    assert _c("hi", "32", on=False) == "hi"


def test_print_verdict_is_plain_and_parseable_in_non_tty(capsys):
    # Under pytest stdout is not a tty, so colour is off: the output must be escape-free and
    # carry the headline substrings tooling parses (the banner and the summary count line).
    verdict = Verdict(
        outcome=Outcome.PASS,
        rationale="all good",
        findings=(
            Finding(
                source="clerk:word_count", severity=Severity.INFO, message="12 words", id="c#0"
            ),
        ),
    )
    _print_verdict(verdict)
    out = capsys.readouterr().out
    assert "\033[" not in out  # no ANSI escapes leaked into captured (non-tty) output
    assert "VERDICT: PASS" in out
    # The one-line summary with the counts that matter.
    assert "1 findings · 0 advisory · 0 model calls (gated=False)" in out


def test_print_verdict_shows_advisory_section_when_present(capsys):
    verdict = Verdict(
        outcome=Outcome.PASS,
        rationale="all good",
        findings=(
            Finding(source="clerk:word_count", severity=Severity.INFO, message="ok", id="c#0"),
            Finding(
                source="council:accuracy",
                severity=Severity.LOW,
                message="a beyond-spec note",
                id="council:accuracy#1",
                advisory=True,
            ),
        ),
    )
    _print_verdict(verdict)
    out = capsys.readouterr().out
    # Advisory is counted separately in the summary and printed in its own section below.
    assert "1 findings · 1 advisory · 0 model calls" in out
    assert "Also noted — advisory (beyond the stated spec):" in out
    assert "a beyond-spec note" in out


def test_print_verdict_no_color_flag_forces_plain(capsys):
    # Even if something upstream thought colour was on, --no-color (no_color=True) wins.
    verdict = Verdict(outcome=Outcome.FAIL, rationale="nope")
    _print_verdict(verdict, no_color=True)
    out = capsys.readouterr().out
    assert "\033[" not in out
    assert "VERDICT: FAIL" in out
