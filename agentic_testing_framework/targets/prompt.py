"""Drive a single-turn, provider-backed prompt agent as the agent under test."""

from __future__ import annotations

from ..providers.base import Provider


class PromptTarget:
    def __init__(self, provider: Provider, *, system: str = "", name: str = "prompt") -> None:
        self.provider = provider
        self.system = system
        self.name = name

    def run(self, input: str) -> str:
        return self.provider.complete(self.system, input)
