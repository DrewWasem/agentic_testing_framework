"""Target seam: function, prompt, cli, http (monkeypatched), and the case runner."""

import json
import sys

from agentic_testing_framework import (
    CliTarget,
    FunctionTarget,
    HttpTarget,
    MockProvider,
    PromptTarget,
    run_target,
)


def test_function_target():
    assert FunctionTarget(lambda s: s.upper()).run("hi") == "HI"


def test_prompt_target_uses_provider():
    target = PromptTarget(MockProvider(default="resp"), system="sys")
    assert target.run("in") == "resp"


def test_cli_target_echo():
    target = CliTarget(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"]
    )
    assert target.run("hello") == "HELLO"


def test_http_target_parses_json(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, body):
            self._body = body.encode("utf-8")

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        captured["data"] = request.data
        return FakeResponse(json.dumps({"output": "the answer"}))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    target = HttpTarget("http://example.test/run")
    assert target.run("q") == "the answer"
    assert b'"input": "q"' in captured["data"]


def test_run_target_builds_case():
    case = run_target(FunctionTarget(lambda s: s + "!"), "hi", "expectation", ["c"])
    assert case.output == "hi!"
    assert case.input == "hi"
    assert case.criteria == ("c",)
