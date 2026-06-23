"""The one-call convenience layer: ``evaluate`` a result without wiring the pipeline.

Building a :class:`Case`, a pipeline, and running it is three steps; for the common
"I have an output, judge it against this expectation" case that is more ceremony than the
task deserves. ``evaluate`` collapses it to a single call with sensible defaults — offline
and free unless you pass a real provider — while leaving the full ``Case`` + ``build_pipeline``
+ ``run_case`` path untouched for everything more involved.
"""

from __future__ import annotations

from collections.abc import Sequence

from .core.case import Case
from .core.types import Verdict
from .providers.base import Provider
from .providers.mock import MockProvider
from .tribunal.checks import Check
from .tribunal.pipeline import build_pipeline


def evaluate(
    input: str,
    output: str,
    expectation: str,
    *,
    criteria: Sequence[str] | None = None,
    provider: Provider | None = None,
    checks: Sequence[Check] | None = None,
    lenses: Sequence[str] | None = None,
) -> Verdict:
    """Judge an existing ``output`` against an ``expectation`` and return the :class:`Verdict`.

    Builds the :class:`Case`, builds a pipeline (offline ``MockProvider`` by default — no API
    key, no network), runs it, and hands back the adjudicated verdict with its full evidence
    ledger. Pass a real ``provider`` for a live run, or override the deterministic ``checks``
    or the council ``lenses`` exactly as :func:`build_pipeline` allows.

    Example::

        from agentic_testing_framework import evaluate

        verdict = evaluate("What is 2+2?", "4", "States that the answer is 4")
        print(verdict.outcome, verdict.rationale)
    """

    case = Case(
        input=input,
        output=output,
        expectation=expectation,
        criteria=tuple(criteria) if criteria is not None else (),
    )
    pipeline = build_pipeline(provider or MockProvider(), checks=checks, lenses=lenses)
    return pipeline.run_case(case)
