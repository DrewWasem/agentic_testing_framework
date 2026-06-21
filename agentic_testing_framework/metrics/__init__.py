"""Metrics — a library of named LLM-judge lenses that write to the evidence ledger.

Each metric (G-Eval, faithfulness, answer relevancy, hallucination, toxicity) is a
reviewer-style lens, not a deterministic check: it asks a model to score one axis of the
agent's output and records a structured :class:`~agentic_testing_framework.core.finding.Finding`
whose numeric score lives in ``metadata`` -- so a metric result is as auditable as any
council finding. They are **opt-in and standalone**: nothing here runs in the default
pipeline. ``run_metrics`` evaluates a set of them and aggregates the scores (the one place
averaging is allowed -- never the orchestrator). Everything runs offline via the mock.
"""

from __future__ import annotations

from .answer_relevancy import AnswerRelevancy
from .base import Metric
from .faithfulness import Faithfulness
from .g_eval import GEval
from .hallucination import Hallucination
from .registry import METRICS, get_metric
from .suite import MetricReport, run_metrics
from .toxicity import Toxicity

__all__ = [
    "METRICS",
    "AnswerRelevancy",
    "Faithfulness",
    "GEval",
    "Hallucination",
    "Metric",
    "MetricReport",
    "Toxicity",
    "get_metric",
    "run_metrics",
]
