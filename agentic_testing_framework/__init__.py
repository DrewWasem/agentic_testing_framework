"""Agentic Testing Framework — an adversarial test harness with an auditable tribunal.

The public API is re-exported here so callers can ``from agentic_testing_framework import Case``.
Importing this package pulls in **no third-party dependency**: model SDKs live behind the
provider seam and are imported lazily, only when a real backend is actually used.
"""

from __future__ import annotations

from .api import evaluate
from .core.case import Case
from .core.finding import Finding
from .core.ledger import EvidenceLedger
from .core.metrics import MetricsSummary, summarize
from .core.models import Tier
from .core.parsing import JSONParseError
from .core.types import Outcome, Severity, StageCost, Verdict
from .generator.adaptive import AdaptiveLoop, AdaptiveReport
from .generator.adversarial import (
    ADVERSARIAL_CATEGORIES,
    INJECTION_CANARY,
    AdversarialGenerator,
    injection_leak_check,
)
from .generator.mutation import Mutator
from .generator.spec import GenSpec, SpecGenerator
from .metaeval import (
    BASELINE_SYSTEM,
    CaseRow,
    JudgeScores,
    LabeledCase,
    MetaEvalReport,
    cohens_kappa,
    confusion_matrix,
    gaming_pipeline,
    hollow_case,
    is_gamed,
    load_labeled,
    precision_recall,
    raw_agreement,
    render_markdown,
    run_metaeval,
    save_labeled,
    single_judge,
)
from .metrics import (
    AnswerRelevancy,
    Faithfulness,
    GEval,
    Hallucination,
    Metric,
    MetricReport,
    Toxicity,
    get_metric,
    run_metrics,
)
from .prompts import PROMPTS, Prompt, get_prompt
from .providers.base import CountingProvider, Provider
from .providers.cache import CachingProvider
from .providers.claude_cli import ClaudeCLIProvider
from .providers.mock import MockProvider
from .providers.registry import get_provider, register_provider
from .regression import (
    GoldenCase,
    GoldenSet,
    RegressionReport,
    RegressionResult,
    load_golden,
    run_regression,
    save_golden,
    update_baseline,
)
from .reporting import render_html, render_junit, render_suite_html
from .targets.base import Target
from .targets.cli import CliTarget
from .targets.function import FunctionTarget
from .targets.http import HttpTarget
from .targets.prompt import PromptTarget
from .targets.runner import run_target
from .tribunal.checks import (
    ForbiddenPatternCheck,
    JSONValidityCheck,
    NonEmptyCheck,
    RequiredPatternCheck,
    ScoreThresholdCheck,
    SentenceLengthCheck,
    URLValidityCheck,
    WordCountCheck,
    default_checks,
)
from .tribunal.clerk import Check, Clerk, ClerkResult
from .tribunal.council import Council
from .tribunal.orchestrator import Orchestrator
from .tribunal.pipeline import Pipeline, build_pipeline
from .tribunal.reviewer import Reviewer

__version__ = "0.1.0"

__all__ = [
    "ADVERSARIAL_CATEGORIES",
    "BASELINE_SYSTEM",
    "AdaptiveLoop",
    "AdaptiveReport",
    "AdversarialGenerator",
    "AnswerRelevancy",
    "CachingProvider",
    "Case",
    "CaseRow",
    "Check",
    "ClaudeCLIProvider",
    "CliTarget",
    "Clerk",
    "ClerkResult",
    "Council",
    "CountingProvider",
    "EvidenceLedger",
    "Faithfulness",
    "Finding",
    "ForbiddenPatternCheck",
    "FunctionTarget",
    "GEval",
    "GenSpec",
    "GoldenCase",
    "GoldenSet",
    "Hallucination",
    "HttpTarget",
    "INJECTION_CANARY",
    "JSONParseError",
    "JSONValidityCheck",
    "JudgeScores",
    "LabeledCase",
    "Metric",
    "MetaEvalReport",
    "MetricReport",
    "MetricsSummary",
    "MockProvider",
    "Mutator",
    "NonEmptyCheck",
    "Orchestrator",
    "Outcome",
    "PROMPTS",
    "Pipeline",
    "Prompt",
    "PromptTarget",
    "Provider",
    "RegressionReport",
    "RegressionResult",
    "RequiredPatternCheck",
    "Reviewer",
    "ScoreThresholdCheck",
    "SentenceLengthCheck",
    "Severity",
    "SpecGenerator",
    "StageCost",
    "Target",
    "Tier",
    "Toxicity",
    "URLValidityCheck",
    "Verdict",
    "WordCountCheck",
    "__version__",
    "build_pipeline",
    "cohens_kappa",
    "confusion_matrix",
    "default_checks",
    "evaluate",
    "gaming_pipeline",
    "get_metric",
    "get_prompt",
    "get_provider",
    "hollow_case",
    "injection_leak_check",
    "is_gamed",
    "load_golden",
    "load_labeled",
    "precision_recall",
    "raw_agreement",
    "register_provider",
    "render_html",
    "render_junit",
    "render_markdown",
    "render_suite_html",
    "run_metaeval",
    "run_metrics",
    "run_regression",
    "run_target",
    "save_golden",
    "save_labeled",
    "single_judge",
    "summarize",
    "update_baseline",
]
