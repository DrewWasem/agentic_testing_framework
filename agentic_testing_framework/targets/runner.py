"""Drive a target on an input and package the result as a gradeable Case."""

from __future__ import annotations

from collections.abc import Sequence

from ..core.case import Case
from .base import Target


def run_target(
    target: Target,
    input: str,
    expectation: str,
    criteria: Sequence[str] = (),
) -> Case:
    output = target.run(input)
    return Case(input=input, expectation=expectation, output=output, criteria=criteria)
