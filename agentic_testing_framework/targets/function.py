"""Drive a plain Python callable as the agent under test."""

from __future__ import annotations

from collections.abc import Callable


class FunctionTarget:
    def __init__(self, fn: Callable[[str], str], *, name: str = "function") -> None:
        self._fn = fn
        self.name = name

    def run(self, input: str) -> str:
        return self._fn(input)
