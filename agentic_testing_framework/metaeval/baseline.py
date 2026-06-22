"""The single-judge baseline — the unstructured judge ATF claims to beat.

One model call, a naive prompt ("is this output good? PASS/FAIL + reason"), and a tolerant
parse to an :class:`Outcome`. No deterministic grounding, no council, no adjudication — the
whole point is that this is the lenient one-shot judge a structured tribunal is supposed to
outperform on the subtle-bad cases. Meta-eval runs this beside the full tribunal on the same
labeled set and scores both against the human gold labels.

The prompt is role-tagged (``[atf-role=baseline]``) so the offline mock can answer it, and it
reuses the metric prompt's ``AGENT OUTPUT:`` block layout so the mock's output-quoting regex
works unchanged. Parsing mirrors the council/reviewer tolerance (:func:`_coerce_passed`):
``"pass"``/``"fail"`` and the usual truthy/falsey synonyms all map correctly, and anything
unrecognized fails closed to FAIL rather than silently passing a bad output.
"""

from __future__ import annotations

from ..core.case import Case
from ..core.llm import complete_json
from ..core.parsing import JSONParseError
from ..core.roles import ROLE_BASELINE, role_header
from ..core.types import Outcome
from ..providers.base import Provider
from ..tribunal._judging import _coerce_passed

# A deliberately unstructured judge prompt: no criteria-by-criteria walk, no grounding facts,
# no adversarial lens — just "is this good?". That naivety is what meta-eval exposes.
BASELINE_SYSTEM = (
    "You are evaluating an AI agent's output. Given the TASK, the EXPECTATION of a good "
    "result, and the agent's OUTPUT, decide whether the output is good. "
    'Respond with ONLY a JSON object of the form {"verdict": "pass"|"fail", "reason": str}.'
)


def _render_prompt(case: Case) -> str:
    return (
        f"TASK:\n{case.input}\n\n"
        f"EXPECTATION:\n{case.expectation}\n\n"
        f"AGENT OUTPUT:\n{case.output or '(empty output)'}\n\n"
        "Is the output good? Answer with the JSON object.\n"
    )


def single_judge(case: Case, provider: Provider) -> Outcome:
    """Rule on ``case`` with one naive model call; return :class:`Outcome` PASS or FAIL.

    Tolerant of the model's phrasing via the shared ``_coerce_passed`` (so ``"pass"``,
    ``True``, ``"yes"`` → PASS and ``"fail"``, ``False``, ``"no"`` → FAIL). An unparseable
    response or an unrecognized verdict **fails closed to FAIL** — a baseline that cannot
    decide should not be credited with a PASS, and meta-eval would otherwise reward a judge
    for emitting garbage on a hard case. This is binary by construction: a single judge never
    returns the tribunal's ``inconclusive``.
    """

    system = f"{role_header(ROLE_BASELINE)}\n{BASELINE_SYSTEM}"
    try:
        data = complete_json(provider, system, _render_prompt(case))
    except JSONParseError:
        return Outcome.FAIL
    verdict = _coerce_passed(data.get("verdict"))
    return Outcome.PASS if verdict is True else Outcome.FAIL
