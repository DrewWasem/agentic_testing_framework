"""Golden-set regression — catch verdict drift after a prompt or model change.

A golden set is a small JSON baseline of cases paired with the outcome the tribunal is
*expected* to reach. :func:`run_regression` re-runs each case and reports the flips — cases
whose ruling no longer matches the baseline — as a fraction (``drift``) gated by a budget,
so a prompt edit that quietly broke a verdict fails CI instead of slipping through. The
comparison is on the verdict's ``Outcome`` property, never on the rationale prose.

Everything is stdlib-only (``json`` + ``pathlib``) and runs offline through the same
pipeline as the rest of the framework. The top-level package re-exports the public names.
"""

from __future__ import annotations

from .golden import GoldenCase, GoldenSet, load_golden, save_golden
from .runner import (
    RegressionReport,
    RegressionResult,
    run_regression,
    update_baseline,
)

__all__ = [
    "GoldenCase",
    "GoldenSet",
    "RegressionReport",
    "RegressionResult",
    "load_golden",
    "run_regression",
    "save_golden",
    "update_baseline",
]
