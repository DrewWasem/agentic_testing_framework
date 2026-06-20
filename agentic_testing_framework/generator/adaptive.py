"""The adaptive loop (opt-in) — feed verdicts back to target an agent's weak spots.

Run a batch of cases, see which robustness categories the agent failed, then generate
more cases in exactly those categories and run again. This shifts effort toward where the
agent actually breaks rather than re-testing what already passes.

Regeneration is per failing case: each failing case spawns more probes of its OWN failing
category, derived from its OWN base input — so with a heterogeneous seed set the loop
keeps probing the right target instead of grafting one seed's category onto another.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..core.case import Case
from ..core.types import Outcome, Verdict
from ..targets.base import Target
from ..tribunal.pipeline import Pipeline
from .adversarial import ADVERSARIAL_CATEGORIES, AdversarialGenerator


@dataclass
class AdaptiveReport:
    rounds: int
    cases_run: int
    verdicts: list[Verdict]
    failures_by_category: dict[str, int]


class AdaptiveLoop:
    def __init__(
        self,
        pipeline: Pipeline,
        adversarial: AdversarialGenerator | None = None,
        *,
        target: Target | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._adversarial = adversarial or AdversarialGenerator()
        self._target = target

    def run(self, seeds: Sequence[Case], *, rounds: int = 2) -> AdaptiveReport:
        if not seeds:
            return AdaptiveReport(rounds=0, cases_run=0, verdicts=[], failures_by_category={})

        failures: dict[str, int] = {}
        verdicts: list[Verdict] = []
        cases = list(seeds)
        completed = 0
        for round_index in range(max(1, rounds)):
            completed = round_index + 1
            # (failing case, its failing category) — used to regenerate from the right base.
            failed: list[tuple[Case, str]] = []
            for case in cases:
                materialized = self._materialize(case)
                verdict = self._pipeline.run_case(materialized)
                verdicts.append(verdict)
                category = str(materialized.metadata.get("category", "uncategorized"))
                if verdict.outcome is Outcome.FAIL:
                    failures[category] = failures.get(category, 0) + 1
                    if category in ADVERSARIAL_CATEGORIES:
                        failed.append((case, category))
            if not failed:
                break
            cases = []
            for case, category in failed:
                cases.extend(AdversarialGenerator([category]).generate(self._base_case(case)))

        return AdaptiveReport(
            rounds=completed,
            cases_run=len(verdicts),
            verdicts=verdicts,
            failures_by_category=failures,
        )

    def _base_case(self, case: Case) -> Case:
        """Recover the original (pre-perturbation) case to re-probe its weak category."""

        base_input = case.metadata.get("base_input")
        if isinstance(base_input, str):
            return Case(input=base_input, expectation=case.expectation, criteria=case.criteria)
        return case

    def _materialize(self, case: Case) -> Case:
        if case.output is None and self._target is not None:
            return Case(
                input=case.input,
                expectation=case.expectation,
                output=self._target.run(case.input),
                criteria=case.criteria,
                metadata=case.metadata,
            )
        return case
