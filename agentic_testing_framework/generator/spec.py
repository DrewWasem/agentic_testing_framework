"""Spec-driven generation — invent diverse cases from a plain-English task description.

Degrades gracefully: if the model returns nothing usable (or no model is wired), it
falls back to deterministic spec-templated cases so generation never silently produces
zero cases.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..core.case import Case
from ..core.llm import complete_json
from ..core.parsing import JSONParseError
from ..core.roles import ROLE_GENERATOR, role_header
from ..prompts import get_prompt
from ..providers.base import Provider

# Prompt-as-code: the generator's system text is versioned in the registry. ``PROMPT_ID`` is
# its key; ``GENERATOR_SYSTEM`` stays as a module-level alias of the registered text.
PROMPT_ID = "generator"
GENERATOR_SYSTEM = get_prompt(PROMPT_ID).text


@dataclass
class GenSpec:
    task: str
    expectation: str
    criteria: Sequence[str] = ()
    n: int = 3


class SpecGenerator:
    def __init__(self, provider: Provider, *, max_retries: int = 1) -> None:
        self._provider = provider
        self._max_retries = max_retries

    def generate(self, spec: GenSpec) -> list[Case]:
        system = f"{role_header(ROLE_GENERATOR)}\n{GENERATOR_SYSTEM}"
        prompt = f"TASK:\n{spec.task}\n\nDEFAULT EXPECTATION:\n{spec.expectation}\n\nN = {spec.n}\n"
        try:
            data = complete_json(self._provider, system, prompt, max_retries=self._max_retries)
        except JSONParseError:
            return self._fallback(spec)
        return self._parse(data, spec) or self._fallback(spec)

    def _parse(self, data: dict[str, Any], spec: GenSpec) -> list[Case]:
        raw = data.get("cases")
        if not isinstance(raw, list):
            return []
        cases: list[Case] = []
        for item in raw:
            if not isinstance(item, dict) or "input" not in item:
                continue
            criteria = item.get("criteria")
            cases.append(
                Case(
                    input=str(item["input"]),
                    expectation=str(item.get("expectation", spec.expectation)),
                    criteria=(
                        [str(c) for c in criteria]
                        if isinstance(criteria, list)
                        else list(spec.criteria)
                    ),
                    metadata={"source": "spec-generator"},
                )
            )
        return cases

    @staticmethod
    def _fallback(spec: GenSpec) -> list[Case]:
        return [
            Case(
                input=f"{spec.task} (variant {i + 1})",
                expectation=spec.expectation,
                criteria=list(spec.criteria),
                metadata={"source": "spec-generator-fallback", "variant": i + 1},
            )
            for i in range(spec.n)
        ]
