"""Run a set of named metrics and aggregate their scores.

This is the one place metric scores are averaged — deliberately HERE and never in the
orchestrator, whose job is to adjudicate disagreement, not collapse it. Each metric still
writes its own structured finding into the shared ledger; the aggregate is a convenience
rollup computed over those findings, not a substitute for them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..core.case import Case
from ..core.finding import Finding
from ..core.ledger import EvidenceLedger
from ..providers.base import Provider
from .registry import get_metric


@dataclass(frozen=True)
class MetricReport:
    """The result of a metric run: per-metric scores, the findings, and an aggregate.

    ``scores`` maps each metric name to its normalized 0..1 score (``None`` if the metric
    could not produce a number). ``mean`` is the average over the numeric scores, and
    ``passed`` is whether that mean clears ``threshold``.
    """

    scores: dict[str, float | None]
    findings: tuple[Finding, ...]
    mean: float
    threshold: float
    passed: bool
    ledger: EvidenceLedger = field(repr=False)


def run_metrics(
    case: Case,
    provider: Provider,
    *,
    metrics: Sequence[str],
    ledger: EvidenceLedger | None = None,
    threshold: float = 0.6,
) -> MetricReport:
    """Evaluate ``case`` with each named metric, writing findings into ``ledger``.

    Each metric appends exactly one finding to the ledger (a fresh one if none is given).
    The returned report carries the per-metric scores plus their mean and a pass/fail
    against ``threshold`` -- the averaging the orchestrator is forbidden from doing lives
    here, where collapsing the scores into a single number is the intended behaviour.
    """

    if not metrics:
        raise ValueError("run_metrics requires at least one metric name")

    led = ledger if ledger is not None else EvidenceLedger()
    scores: dict[str, float | None] = {}
    findings: list[Finding] = []
    for name in metrics:
        metric = get_metric(name)
        finding = metric.evaluate(case, provider, led)
        findings.append(finding)
        raw = finding.metadata.get("score")
        scores[name] = (
            float(raw) if isinstance(raw, int | float) and not isinstance(raw, bool) else None
        )

    numeric = [s for s in scores.values() if s is not None]
    mean = sum(numeric) / len(numeric) if numeric else 0.0
    return MetricReport(
        scores=scores,
        findings=tuple(findings),
        mean=round(mean, 4),
        threshold=threshold,
        passed=bool(numeric) and mean >= threshold,
        ledger=led,
    )
