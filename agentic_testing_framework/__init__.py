"""Agentic Testing Framework — an adversarial test harness with an auditable tribunal.

The public API is re-exported here so callers can ``from agentic_testing_framework import Case``.
Importing this package pulls in **no third-party dependency**: model SDKs live behind the
provider seam and are imported lazily, only when a real backend is actually used.
"""

from __future__ import annotations

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
from .providers.base import CountingProvider, Provider
from .providers.claude_cli import ClaudeCLIProvider
from .providers.mock import MockProvider
from .providers.registry import get_provider, register_provider
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
    "AdaptiveLoop",
    "AdaptiveReport",
    "AdversarialGenerator",
    "Case",
    "Check",
    "ClaudeCLIProvider",
    "CliTarget",
    "Clerk",
    "ClerkResult",
    "Council",
    "CountingProvider",
    "EvidenceLedger",
    "Finding",
    "ForbiddenPatternCheck",
    "FunctionTarget",
    "GenSpec",
    "HttpTarget",
    "INJECTION_CANARY",
    "JSONParseError",
    "JSONValidityCheck",
    "MetricsSummary",
    "MockProvider",
    "Mutator",
    "NonEmptyCheck",
    "Orchestrator",
    "Outcome",
    "Pipeline",
    "PromptTarget",
    "Provider",
    "RequiredPatternCheck",
    "Reviewer",
    "ScoreThresholdCheck",
    "SentenceLengthCheck",
    "Severity",
    "SpecGenerator",
    "StageCost",
    "Target",
    "Tier",
    "URLValidityCheck",
    "Verdict",
    "WordCountCheck",
    "__version__",
    "build_pipeline",
    "default_checks",
    "get_provider",
    "injection_leak_check",
    "register_provider",
    "run_target",
    "summarize",
]
