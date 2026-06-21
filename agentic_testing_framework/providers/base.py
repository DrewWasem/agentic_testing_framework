"""The provider protocol and a metering wrapper.

A provider is the whole seam between the framework and a model: one method,
``complete(system, prompt) -> text``. Swapping the backend is a one-file change.
``CountingProvider`` wraps any provider to meter calls, latency, and estimated cost.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

from ..core.models import price_for


@runtime_checkable
class Provider(Protocol):
    """How the framework talks to a judge or generator model."""

    name: str

    def complete(self, system: str, prompt: str) -> str: ...


class CountingProvider:
    """Wraps any provider and meters it: call count, wall-clock latency, estimated cost.

    The pipeline puts one of these around each stage's provider so the verdict can carry a
    per-stage cost rollup. ``model_id`` is the model the stage is *priced at* (its tier's
    default id); leave it ``None`` and every call estimates as free.

    Cost is an honest estimate, not a bill:

    * If ``price_for(model_id)`` is ``None`` (e.g. the offline mock, or any unpriced model),
      every call costs ``0.0``.
    * Otherwise tokens are approximated from the *actual* text — ``len(system+prompt)/4``
      in, ``len(response)/4`` out — and priced at the model's list price per million tokens.
    * A cache hit costs ``0.0`` and adds ~0 latency. A hit is detected by reading the inner
      provider's ``misses`` counter before/after the call: if it did **not** increase, the
      response came from disk, so it is not charged. An inner with no ``misses`` attribute
      (no cache in the stack) means every call is a real call and is priced.
    """

    def __init__(self, inner: Provider, *, model_id: str | None = None) -> None:
        self.inner = inner
        self.name = inner.name
        self.model_id = model_id
        self.calls = 0
        self.latency_s = 0.0
        self.cost_usd = 0.0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        misses_before = getattr(self.inner, "misses", None)
        start = time.perf_counter()
        response = self.inner.complete(system, prompt)
        elapsed = time.perf_counter() - start
        self.latency_s += elapsed
        misses_after = getattr(self.inner, "misses", None)
        was_cache_hit = misses_before is not None and misses_after == misses_before
        if not was_cache_hit:
            self.cost_usd += self._estimate_cost(system, prompt, response)
        return response

    def _estimate_cost(self, system: str, prompt: str, response: str) -> float:
        price = price_for(self.model_id)
        if price is None:
            return 0.0
        in_tok = len(system) + len(prompt)
        out_tok = len(response)
        return in_tok / 4 / 1e6 * price.input_per_mtok + out_tok / 4 / 1e6 * price.output_per_mtok

    def reset(self) -> None:
        self.calls = 0
        self.latency_s = 0.0
        self.cost_usd = 0.0
