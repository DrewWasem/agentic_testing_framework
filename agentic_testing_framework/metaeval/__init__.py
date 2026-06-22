"""Meta-evaluation — prove the judge, don't just assert it.

The framework's pitch is "better evaluation", which is unproven until the tribunal's
*judgement quality* is measured against ground truth. This package does that: it scores the
full ATF tribunal against a naive **single-judge baseline** on a **hand-labeled** dataset,
measuring each judge's agreement with the human gold labels (raw agreement, Cohen's kappa,
and fail-class precision/recall — catching bad output is the high-value job).

Everything here runs offline against the mock for tests; the real-judge run (via the
``ClaudeCLIProvider``) is reachable from ``atf metaeval --judge claude-cli`` but is never
exercised by a test. All agreement math is stdlib-only and lives in :mod:`agreement`, never
in the orchestrator (whose job is to adjudicate, not average). The top-level package
re-exports the public names.
"""

from __future__ import annotations

from .agreement import (
    Pair,
    cohens_kappa,
    confusion_matrix,
    precision_recall,
    raw_agreement,
)
from .baseline import BASELINE_SYSTEM, single_judge
from .dataset import LabeledCase, load_labeled, save_labeled
from .gaming import gaming_pipeline, hollow_case, is_gamed
from .runner import CaseRow, JudgeScores, MetaEvalReport, render_markdown, run_metaeval

__all__ = [
    "BASELINE_SYSTEM",
    "CaseRow",
    "JudgeScores",
    "LabeledCase",
    "MetaEvalReport",
    "Pair",
    "cohens_kappa",
    "confusion_matrix",
    "gaming_pipeline",
    "hollow_case",
    "is_gamed",
    "load_labeled",
    "precision_recall",
    "raw_agreement",
    "render_markdown",
    "run_metaeval",
    "save_labeled",
    "single_judge",
]
