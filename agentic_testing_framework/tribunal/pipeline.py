"""The pipeline — wires Clerk -> Reviewer -> Council -> Orchestrator end to end.

Gating: a failed hard gate returns a verdict immediately, before any model is called.
Tiering: each LLM stage gets its own provider (wire a cheap model for the reviewer/council
and a frontier model for the orchestrator). Cost: per-stage LLM call counts are recorded
on the verdict via call-counting provider wrappers.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.case import Case
from ..core.ledger import EvidenceLedger
from ..core.types import Outcome, StageCost, Verdict
from ..providers.base import CountingProvider, Provider
from ..providers.mock import MockProvider
from .checks import Check
from .clerk import Clerk
from .council import Council
from .orchestrator import Orchestrator
from .reviewer import Reviewer


class Pipeline:
    def __init__(
        self,
        clerk: Clerk,
        reviewer: Reviewer,
        council: Council,
        orchestrator: Orchestrator,
        *,
        counters: dict[str, CountingProvider] | None = None,
    ) -> None:
        self._clerk = clerk
        self._reviewer = reviewer
        self._council = council
        self._orchestrator = orchestrator
        self._counters = counters or {}

    def run_case(self, case: Case) -> Verdict:
        ledger = EvidenceLedger()
        clerk_result = self._clerk.inspect(case, ledger)
        if clerk_result.gate_failed:
            reason = "; ".join(f.message for f in clerk_result.gate_findings)
            return Verdict(
                outcome=Outcome.FAIL,
                rationale=f"Hard gate failed before any model was called: {reason}",
                cited_findings=tuple(f.id for f in clerk_result.gate_findings),
                gated=True,
                stage_costs=(StageCost("clerk", "deterministic", 0),),
                findings=ledger.findings,
            )
        for counter in self._counters.values():
            counter.reset()
        self._reviewer.review(case, ledger)
        self._council.deliberate(case, ledger)
        verdict = self._orchestrator.adjudicate(case, ledger)
        verdict.gated = False
        verdict.stage_costs = self._stage_costs()
        verdict.findings = ledger.findings
        return verdict

    def run_suite(self, cases: Sequence[Case]) -> list[Verdict]:
        return [self.run_case(case) for case in cases]

    def _stage_costs(self) -> tuple[StageCost, ...]:
        costs = [StageCost("clerk", "deterministic", 0)]
        for stage in ("reviewer", "council", "orchestrator"):
            counter = self._counters.get(stage)
            if counter is not None:
                costs.append(StageCost(stage, counter.name, counter.calls))
        return tuple(costs)


def build_pipeline(
    provider: Provider | None = None,
    *,
    checks: Sequence[Check] | None = None,
    lenses: Sequence[str] | None = None,
    max_retries: int = 1,
) -> Pipeline:
    """Build a ready-to-run pipeline. Defaults to a fully offline ``MockProvider``.

    Pass a real provider (or three, by constructing the components directly) to wire model
    tiering: a cheap model for the reviewer and council, a frontier model for the
    orchestrator.
    """

    base = provider if provider is not None else MockProvider()
    reviewer_provider = CountingProvider(base)
    council_provider = CountingProvider(base)
    orchestrator_provider = CountingProvider(base)
    pipeline = Pipeline(
        Clerk(checks),
        Reviewer(reviewer_provider, max_retries=max_retries),
        Council(council_provider, lenses, max_retries=max_retries),
        Orchestrator(orchestrator_provider, max_retries=max_retries),
        counters={
            "reviewer": reviewer_provider,
            "council": council_provider,
            "orchestrator": orchestrator_provider,
        },
    )
    return pipeline
