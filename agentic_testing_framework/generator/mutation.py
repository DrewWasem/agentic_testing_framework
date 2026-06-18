"""Mutation generation — deterministic perturbations to probe for brittle boundaries."""

from __future__ import annotations

from collections.abc import Callable

from ..core.case import Case

_MUTATIONS: list[tuple[str, Callable[[str], str]]] = [
    ("whitespace", lambda t: "  ".join(t.split()) + "   "),
    ("uppercase", lambda t: t.upper()),
    ("truncate", lambda t: t[: max(1, len(t) // 2)]),
    ("repeat", lambda t: (t + " ") * 2),
    ("unicode_lookalike", lambda t: t.replace("a", "а").replace("e", "е")),
]


class Mutator:
    def mutate(self, base: Case, *, n: int = 4) -> list[Case]:
        cases: list[Case] = []
        for kind, fn in _MUTATIONS[: max(0, n)]:
            cases.append(
                Case(
                    input=fn(base.input),
                    expectation=base.expectation,
                    criteria=list(base.criteria),
                    metadata={"source": "mutation", "mutation": kind, "base_input": base.input},
                )
            )
        return cases
