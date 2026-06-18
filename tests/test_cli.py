"""The atf CLI: version and the offline example run."""

from agentic_testing_framework import __version__
from agentic_testing_framework.cli import main


def test_cli_version(capsys):
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_cli_run_example(capsys):
    assert main(["run", "--example"]) == 0
    out = capsys.readouterr().out
    assert "VERDICT:" in out
    assert "Evidence ledger:" in out
