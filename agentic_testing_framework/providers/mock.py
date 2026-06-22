"""The offline, deterministic provider — the spine of "runs free, no API key".

Tests script exact responses; the example and unconfigured runs fall back to role-aware
canned JSON so the whole pipeline still completes end to end with no network. The auto
orchestrator response is ledger-aware: it reads the rendered evidence ledger out of its
prompt, rules FAIL if any finding failed, and cites the finding ids it saw — so even the
zero-config demo produces a traceable verdict.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from ..core.roles import (
    ROLE_BASELINE,
    ROLE_COUNCIL,
    ROLE_GENERATOR,
    ROLE_METRIC,
    ROLE_ORCHESTRATOR,
    ROLE_REVIEWER,
    detect_role,
)

# Tolerant of whitespace in a finding's source (e.g. "score check#0"), not just "a:b#0".
_FINDING_ID = re.compile(r"\[([^\]]+#\d+)\]")

# The metric lenses tag their role header with the metric name: "[atf-role=metric g_eval]".
_METRIC_NAME = re.compile(r"atf-role=metric\s+(\w+)")
# Lift the agent output out of the rendered metric prompt so the mock can quote a real
# evidence span (a metric that fabricates evidence from thin air would be useless offline).
_OUTPUT_BLOCK = re.compile(r"AGENT OUTPUT:\n(.*?)\n\n", re.DOTALL)


def _auto_orchestrator(prompt: str) -> str:
    """Adjudicate from the ledger rendered in the prompt (offline, deterministic)."""

    cited = _FINDING_ID.findall(prompt)
    failed = "FAIL" in prompt
    if failed:
        rationale = "Offline mock adjudication: at least one finding failed."
    else:
        rationale = "Offline mock adjudication: deterministic checks passed and no finding failed."
    return json.dumps(
        {
            "outcome": "fail" if failed else "pass",
            "rationale": rationale,
            "cited_findings": cited[:5],
        }
    )


def _auto_metric(system: str, prompt: str) -> str:
    """A schema-valid metric score for the offline path: score + reasoning + real evidence.

    Quotes a genuine span from the rendered AGENT OUTPUT so the evidence is grounded, and
    for the G-Eval flagship fabricates the chain-of-thought ``steps`` it would derive, so
    the offline metric exercises the full G-Eval shape (auto-steps then form-fill).
    """

    name_match = _METRIC_NAME.search(system)
    name = name_match.group(1) if name_match else "metric"
    out_match = _OUTPUT_BLOCK.search(prompt)
    evidence = out_match.group(1).strip() if out_match else ""
    evidence = evidence[:120] or "(no output to quote)"
    # Inverse metrics (hallucination, toxicity) score the AMOUNT of the bad thing, so a
    # clean offline result is a LOW raw score there and a HIGH one for the positive metrics.
    # The system prompt says "Score HIGH when ... toxic" for those, so the mock keys off the
    # same wording the real instruction carries rather than hard-coding metric names.
    inverse = "inverse metric" in system
    if inverse:
        payload: dict[str, object] = {
            "score": 1,
            "reasoning": f"Offline mock {name}: no harmful or fabricated content found.",
            "evidence": evidence,
        }
    else:
        payload = {
            "score": 5,
            "reasoning": f"Offline mock {name}: output meets the stated expectation.",
            "evidence": evidence,
        }
    if name == "g_eval":
        payload["steps"] = [
            "Derive the criteria the output must satisfy from the expectation.",
            "Check the output against each derived criterion in turn.",
            "Assign a 1-5 score reflecting how fully the criteria are met.",
        ]
    return json.dumps(payload)


def _auto_baseline(prompt: str) -> str:
    """A naive single-judge ruling for the offline path: lenient PASS by default.

    The single-judge baseline is the unstructured judge ATF claims to beat, so its offline
    stand-in is deliberately lenient — it rules PASS unless the output is plainly empty. That
    is the failure mode meta-eval is built to expose: a confident judge that waves through
    subtly-wrong output. Tests that need a particular baseline ruling script it via
    ``responses=``/``handler=``; this fallthrough only keeps an unconfigured run completing.
    """

    out_match = _OUTPUT_BLOCK.search(prompt)
    output = out_match.group(1).strip() if out_match else ""
    if not output or output == "(empty output)":
        return json.dumps({"verdict": "fail", "reason": "Offline mock baseline: empty output."})
    return json.dumps(
        {"verdict": "pass", "reason": "Offline mock baseline: output looks plausible."}
    )


def _auto_response(system: str, prompt: str) -> str:
    """A valid, schema-correct canned response for whichever stage is calling."""

    role = detect_role(system)
    if role == ROLE_REVIEWER:
        return json.dumps(
            {"findings": [], "summary": "No issues detected against the stated expectation."}
        )
    if role == ROLE_COUNCIL:
        return json.dumps({"findings": [], "summary": "This lens found no issues."})
    if role == ROLE_ORCHESTRATOR:
        return _auto_orchestrator(prompt)
    if role == ROLE_GENERATOR:
        return json.dumps({"cases": []})
    if role == ROLE_METRIC:
        return _auto_metric(system, prompt)
    if role == ROLE_BASELINE:
        return _auto_baseline(prompt)
    return json.dumps({"ok": True})


class MockProvider:
    """Offline provider with three layers of control, checked in order.

    1. ``responses``: a queue, popped one per call — exact scripting for tests.
    2. ``handler``: a callable ``(system, prompt) -> str``.
    3. ``default``: a fixed string.

    If none are configured it returns a role-aware canned JSON response so an
    unconfigured pipeline still runs to completion.
    """

    name = "mock"

    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        handler: Callable[[str, str], str] | None = None,
        default: str | None = None,
    ) -> None:
        self._responses = list(responses) if responses else []
        self._handler = handler
        self._default = default
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if self._responses:
            return self._responses.pop(0)
        if self._handler is not None:
            return self._handler(system, prompt)
        if self._default is not None:
            return self._default
        return _auto_response(system, prompt)

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def reset(self) -> None:
        self.calls.clear()
