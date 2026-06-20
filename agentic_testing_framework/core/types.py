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
    """How much each tribunal stage cost, in model calls (deterministic stages = 0)."""

    stage: str
    provider: str
    llm_calls: int


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
