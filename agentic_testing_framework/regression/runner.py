"""Run a golden set through a pipeline and report verdict drift against the baseline.

The comparison is on the verdict *property* (``Outcome``), never on the rationale text — a
rationale is free prose that a model or a prompt edit will legitimately reword without the
ruling itself changing, so string-diffing it would flag noise as drift. A flip is an
outcome that no longer matches the baseline; ``drift`` is the fraction of cases that
flipped, and the run ``passed`` only if that fraction is within the caller's budget.

This is the CI gate for prompt-as-code: bump a prompt version, re-run the golden set, and a
ruling that the change quietly broke shows up as a flip the budget can block on. The
``Pipeline`` here is duck-typed — anything exposing ``run_case(case) -> Verdict`` works, so
the regression runner stays decoupled from the concrete pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from ..core.case import Case
from ..core.types import Outcome, Verdict
from .golden import GoldenCase, save_golden


class _Pipeline(Protocol):
    """The single method the regression runner needs from a pipeline."""

    def run_case(self, case: Case) -> Verdict: ...


@dataclass(frozen=True)
class RegressionResult:
    """One case's outcome vs. its baseline: ``status`` is ``"match"`` or ``"flip"``."""

    case_id: str
    expected: Outcome
    actual: Outcome
    status: str  # "match" | "flip"

    @property
    def flipped(self) -> bool:
        return self.status == "flip"


@dataclass(frozen=True)
class RegressionReport:
    """The drift report: per-case results plus the rolled-up drift and pass/fail.

    ``drift`` is ``flips / total`` (0.0 for an empty set), and ``passed`` is whether that
    fraction is within ``max_drift`` — the budget the CI gate enforces.
    """

    results: tuple[RegressionResult, ...]
    flips: int
    total: int
    drift: float
    max_drift: float
    passed: bool

    @property
    def flipped(self) -> tuple[RegressionResult, ...]:
        """Just the cases whose outcome no longer matches the baseline."""

        return tuple(r for r in self.results if r.flipped)


def run_regression(
    golden: Iterable[GoldenCase],
    pipeline: _Pipeline,
    *,
    max_drift: float = 0.0,
) -> RegressionReport:
    """Run each golden case through ``pipeline`` and compare its outcome to the baseline.

    Drift is ``flips / total`` and the run ``passed`` iff ``drift <= max_drift``. With the
    default ``max_drift=0.0`` any single flip fails the run — the strict gate. The
    comparison is ``verdict.outcome`` (a property) against the baseline outcome; the
    rationale is never inspected.
    """

    results: list[RegressionResult] = []
    flips = 0
    for gc in golden:
        actual = pipeline.run_case(gc.case).outcome
        status = "match" if actual is gc.expected else "flip"
        if status == "flip":
            flips += 1
        results.append(RegressionResult(gc.case_id, gc.expected, actual, status))
    total = len(results)
    drift = flips / total if total else 0.0
    return RegressionReport(
        results=tuple(results),
        flips=flips,
        total=total,
        drift=drift,
        max_drift=max_drift,
        passed=drift <= max_drift,
    )


def update_baseline(
    golden_path: str,
    pipeline: _Pipeline,
    golden: Iterable[GoldenCase],
) -> list[GoldenCase]:
    """Re-run the golden set and rewrite ``golden_path`` with the current outcomes as expected.

    This is the ``--update-baseline`` operation: after an intentional prompt/model change you
    accept the new rulings as the contract. Returns the updated golden cases (also written to
    disk), so a previously-failing set now matches itself.
    """

    updated = [GoldenCase(gc.case_id, gc.case, pipeline.run_case(gc.case).outcome) for gc in golden]
    save_golden(golden_path, updated)
    return updated
