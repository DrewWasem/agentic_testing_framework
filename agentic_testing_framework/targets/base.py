"""The target protocol: drive any agent through one method, ``run(input) -> output``.

A prompt, an HTTP endpoint, a CLI, a local function — if you can call it, you can probe
it. Pointing the harness at a different agent is a one-file change.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Target(Protocol):
    def run(self, input: str) -> str: ...
