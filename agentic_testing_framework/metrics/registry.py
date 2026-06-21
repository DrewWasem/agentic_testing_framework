"""The metric registry — bare names to metric instances, plus a clear lookup error.

Mirrors the provider registry's shape: a dict of singletons and a ``get_metric`` that fails
loudly (listing the valid names) on an unknown key, rather than returning ``None`` and
deferring the error to a confusing ``AttributeError`` later.
"""

from __future__ import annotations

from .answer_relevancy import AnswerRelevancy
from .base import Metric
from .faithfulness import Faithfulness
from .g_eval import GEval
from .hallucination import Hallucination
from .toxicity import Toxicity

# Bare metric names -> singleton instances. Metrics are stateless, so one instance is reused.
METRICS: dict[str, Metric] = {
    GEval.name: GEval(),
    Faithfulness.name: Faithfulness(),
    AnswerRelevancy.name: AnswerRelevancy(),
    Hallucination.name: Hallucination(),
    Toxicity.name: Toxicity(),
}


def get_metric(name: str) -> Metric:
    """Return the metric registered under ``name``, or raise a clear ``KeyError``."""

    try:
        return METRICS[name]
    except KeyError:
        known = ", ".join(sorted(METRICS))
        raise KeyError(f"unknown metric {name!r}; known metrics: {known}") from None
