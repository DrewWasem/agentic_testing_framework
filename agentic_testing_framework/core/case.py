"""The ``Case`` — a unit of work for the tribunal.

You can hand it a result that already exists (set ``output``), or let a target produce
the output by running the input. ``expectation`` is the plain-English bar to clear;
``criteria`` are optional, graded one by one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Case:
    input: str
    expectation: str
    output: str | None = None
    criteria: Sequence[str] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalise to a tuple so callers can pass a list without it being mutated later.
        self.criteria = tuple(self.criteria)
