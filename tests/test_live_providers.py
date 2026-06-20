"""The live provider paths, exercised fully offline (no network, no real CLI/SDK)."""

import subprocess
import sys
import types

import pytest

from agentic_testing_framework import ClaudeCLIProvider
from agentic_testing_framework.providers.anthropic import AnthropicProvider


def test_claude_cli_builds_command_and_pipes_prompt(monkeypatch):
    captured = {}

    class FakeCompleted:
        returncode = 0
        stdout = "CLI SAID HI"
        stderr = ""

    def fake_run(cmd, *, input, capture_output, text, timeout, check):
        captured["cmd"] = cmd
        captured["input"] = input
        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = ClaudeCLIProvider(model="claude-haiku-4-5").complete("SYS", "PROMPT")

    assert out == "CLI SAID HI"
    assert captured["cmd"][:4] == ["claude", "-p", "--output-format", "text"]
    assert "--model" in captured["cmd"] and "claude-haiku-4-5" in captured["cmd"]
    assert "SYS" in captured["input"] and "PROMPT" in captured["input"]


def test_claude_cli_nonzero_exit_raises(monkeypatch):
    class FakeCompleted:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompleted())
    with pytest.raises(RuntimeError, match="claude CLI exited 1"):
        ClaudeCLIProvider().complete("s", "p")


def test_anthropic_provider_builds_request_and_extracts_text(monkeypatch):
    captured = {}

    class FakeBlock:
        type = "text"
        text = "MODEL TEXT"

    class FakeMessage:
        content = [FakeBlock()]

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeMessage()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.messages = FakeMessages()

    fake_sdk = types.ModuleType("anthropic")
    fake_sdk.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)

    out = AnthropicProvider(model="claude-opus-4-8").complete("SYS", "PROMPT")

    assert out == "MODEL TEXT"
    assert captured["model"] == "claude-opus-4-8"
    assert captured["system"] == "SYS"
    assert captured["messages"][0]["content"] == "PROMPT"
    assert captured["temperature"] == 0.0


def test_anthropic_provider_missing_sdk_raises(monkeypatch):
    # A None entry in sys.modules makes `import anthropic` raise ImportError.
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(RuntimeError, match="anthropic"):
        AnthropicProvider().complete("s", "p")
