"""The atf CLI: version, the offline example run, and evaluating an arbitrary case."""

import json

import pytest

from agentic_testing_framework import __version__, cli
from agentic_testing_framework.cli import main


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
