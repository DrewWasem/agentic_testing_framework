"""The pipeline — wires Clerk -> Reviewer -> Council -> Orchestrator end to end.

Gating: a failed hard gate returns a verdict immediately, before any model is called.
Tiering: each LLM stage gets its own metering provider (the reviewer/council are priced at
the CHEAP tier, the orchestrator at the FRONTIER tier). Cost: per-stage call count, latency,
and estimated dollars are recorded on the verdict via the wrapper providers.

Caching: pass ``cache_dir`` and the base provider is wrapped once in a content-addressed
on-disk cache *inside* the per-stage meters, so a cache hit still counts as the call the
case logically needed but costs $0 and adds ~0 latency — that is how the rollup demonstrates
cost by construction. The dollar figure is an *estimate* at default-tier list prices (one
provider runs every stage offline), reflecting the intended tiering, not an actual bill.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.case import Case
from ..core.ledger import EvidenceLedger
from ..core.models import DEFAULT_MODELS, Tier
from ..core.types import Outcome, StageCost, Verdict
from ..providers.base import CountingProvider, Provider
from ..providers.cache import CachingProvider
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
        # The clerk is deterministic — free, instant, never a model call.
        costs = [StageCost("clerk", "deterministic", 0)]
        for stage in ("reviewer", "council", "orchestrator"):
            counter = self._counters.get(stage)
            if counter is not None:
                costs.append(
                    StageCost(
                        stage,
                        counter.name,
                        counter.calls,
                        latency_s=counter.latency_s,
                        cost_usd=counter.cost_usd,
                    )
                )
        return tuple(costs)


def build_pipeline(
    provider: Provider | None = None,
    *,
    checks: Sequence[Check] | None = None,
    lenses: Sequence[str] | None = None,
    max_retries: int = 1,
    cache_dir: str | None = None,
) -> Pipeline:
    """Build a ready-to-run pipeline. Defaults to a fully offline ``MockProvider``.

    Pass a real provider (or three, by constructing the components directly) to wire model
    tiering: a cheap model for the reviewer and council, a frontier model for the
    orchestrator.

    ``cache_dir`` turns on a content-addressed on-disk cache shared by every stage: the base
    provider is wrapped once, then each stage's meter wraps *that*, so a cache hit still
    counts toward the call total but is charged $0 with ~0 latency.

    Each stage's meter is priced at the model that stage *intends* to run on — the reviewer
    and council at ``DEFAULT_MODELS[Tier.CHEAP]``, the orchestrator at
    ``DEFAULT_MODELS[Tier.FRONTIER]``. With the offline mock (unpriced) every estimate is
    $0; with a priced model the cost is estimated from the actual prompt/response text at
    default-tier list prices. It is an estimate, not a bill.
    """

    base = provider if provider is not None else MockProvider()
    shared = CachingProvider(base, cache_dir) if cache_dir else base
    cheap = DEFAULT_MODELS[Tier.CHEAP]
    frontier = DEFAULT_MODELS[Tier.FRONTIER]
    reviewer_provider = CountingProvider(shared, model_id=cheap)
    council_provider = CountingProvider(shared, model_id=cheap)
    orchestrator_provider = CountingProvider(shared, model_id=frontier)
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
