"""Shared enums and the final ``Verdict`` value type.

These are deliberately tiny and dependency-free — they are imported by nearly every
other module, so they must never import anything heavier than the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid a runtime import cycle (finding imports types)
    from .finding import Finding

_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class Severity(str, Enum):
    """How serious a finding is. Ordered via :attr:`rank`."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self.value]


class Outcome(str, Enum):
    """The orchestrator's ruling on a case."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


def severity_from_str(value: str) -> Severity:
    """Coerce a model-supplied string to a :class:`Severity`, defaulting to INFO."""

    try:
        return Severity(value.strip().lower())
    except (ValueError, AttributeError):
        return Severity.INFO


def outcome_from_str(value: str) -> Outcome:
    """Coerce a model-supplied string to an :class:`Outcome`, defaulting to INCONCLUSIVE."""

    try:
        return Outcome(value.strip().lower())
    except (ValueError, AttributeError):
        return Outcome.INCONCLUSIVE


@dataclass(frozen=True)
class StageCost:
    """How much each tribunal stage cost: model calls, wall-clock latency, est. dollars.

    ``latency_s`` is the summed inner-``complete`` wall time for the stage; ``cost_usd`` is
    an *estimate* at default-tier list prices (tokens approximated from the actual text),
    not a bill. Deterministic stages and cache hits are 0 on all three.
    """

    stage: str
    provider: str
    llm_calls: int
    latency_s: float = 0.0
    cost_usd: float = 0.0


@dataclass
class Verdict:
    """The final ruling plus the evidence that produced it.

    ``cited_findings`` holds the ids of the findings the orchestrator leaned on, so any
    verdict is traceable straight back to the ledger.
    """

    outcome: Outcome
    rationale: str
    cited_findings: tuple[str, ...] = ()
    gated: bool = False
    stage_costs: tuple[StageCost, ...] = ()
    findings: tuple[Finding, ...] = ()

    @property
    def passed(self) -> bool:
        return self.outcome is Outcome.PASS

    @property
    def total_llm_calls(self) -> int:
        return sum(c.llm_calls for c in self.stage_costs)

    @property
    def total_latency_s(self) -> float:
        """Summed inner-call latency across stages (cache hits contribute ~0)."""

        return sum(c.latency_s for c in self.stage_costs)

    @property
    def total_cost_usd(self) -> float:
        """Summed estimated cost across stages at default-tier list prices.

        A gated case (or one served entirely from cache) is $0 by construction.
        """

        return sum(c.cost_usd for c in self.stage_costs)
