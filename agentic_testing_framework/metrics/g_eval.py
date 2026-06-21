"""G-Eval — the flagship rubric-scoring metric (auto chain-of-thought, then form-fill).

G-Eval (Liu et al., 2023) is the de-facto LLM-as-judge rubric metric: instead of handing
the model a fixed rubric, you have it *derive* the evaluation steps from the task's own
expectation and criteria first, then form-fill a score by following those steps. Capturing
the derived steps is what makes the score auditable — they land in ``metadata["steps"]``,
so a reader can see the rubric the model graded against, not just the number it returned.
"""

from __future__ import annotations

from typing import Any

from .base import Metric


class GEval(Metric):
    name = "g_eval"
    scale = 5.0
    threshold = 0.6

    @property
    def instruction(self) -> str:
        return (
            "Use the G-Eval method. FIRST, derive an explicit, ordered list of evaluation "
            "STEPS from the EXPECTATION and CRITERIA -- the rubric this specific task "
            "implies (chain-of-thought). THEN follow those steps in order to form-fill a "
            "single overall score. Return the derived steps as a JSON array under the key "
            '"steps" alongside the usual "score", "reasoning", and "evidence" keys, so the '
            "rubric you graded against is recorded."
        )

    def _augment_metadata(self, data: dict[str, Any], metadata: dict[str, Any]) -> None:
        raw_steps = data.get("steps")
        steps: list[str] = []
        if isinstance(raw_steps, list):
            steps = [str(s).strip() for s in raw_steps if str(s).strip()]
        elif isinstance(raw_steps, str) and raw_steps.strip():
            steps = [line.strip() for line in raw_steps.splitlines() if line.strip()]
        metadata["steps"] = steps
