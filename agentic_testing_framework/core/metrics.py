"""Lightweight metrics over a batch of verdicts.

Just enough to summarise a suite run; richer metrics (hallucination rate, latency
percentiles) layer on top of the same verdict/ledger record.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .types import Outcome, Verdict


@dataclass(frozen=True)
class MetricsSummary:
    total: int
    passed: int
    failed: int
    inconclusive: int
    gated: int
    pass_rate: float


def summarize(verdicts: Sequence[Verdict]) -> MetricsSummary:
    total = len(verdicts)
    passed = sum(1 for v in verdicts if v.outcome is Outcome.PASS)
    failed = sum(1 for v in verdicts if v.outcome is Outcome.FAIL)
    inconclusive = sum(1 for v in verdicts if v.outcome is Outcome.INCONCLUSIVE)
    gated = sum(1 for v in verdicts if v.gated)
    pass_rate = passed / total if total else 0.0
    return MetricsSummary(total, passed, failed, inconclusive, gated, pass_rate)
