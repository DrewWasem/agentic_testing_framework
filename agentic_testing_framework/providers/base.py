"""The provider protocol and a call-counting wrapper.

A provider is the whole seam between the framework and a model: one method,
``complete(system, prompt) -> text``. Swapping the backend is a one-file change.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Provider(Protocol):
    """How the framework talks to a judge or generator model."""

    name: str

    def complete(self, system: str, prompt: str) -> str: ...


class CountingProvider:
    """Wraps any provider and counts calls — the pipeline uses this for per-stage cost."""

    def __init__(self, inner: Provider) -> None:
        self.inner = inner
        self.name = inner.name
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        return self.inner.complete(system, prompt)

    def reset(self) -> None:
        self.calls = 0
