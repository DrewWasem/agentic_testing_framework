"""The Claude-CLI provider — offline via an injected runner — and registry resolution."""

from agentic_testing_framework import ClaudeCLIProvider, get_provider


def test_claude_cli_combines_system_and_prompt_and_uses_runner():
    captured = {}

    def fake_runner(full_prompt):
        captured["prompt"] = full_prompt
        return "MODEL OUTPUT"

    provider = ClaudeCLIProvider(runner=fake_runner)
    assert provider.complete("SYSTEM RULES", "the user prompt") == "MODEL OUTPUT"
    assert "SYSTEM RULES" in captured["prompt"]
    assert "the user prompt" in captured["prompt"]


def test_registry_resolves_claude_cli():
    provider = get_provider("claude-cli")
    assert isinstance(provider, ClaudeCLIProvider)
    assert provider.name == "claude-cli"
