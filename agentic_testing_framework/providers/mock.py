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
    ROLE_COUNCIL,
    ROLE_GENERATOR,
    ROLE_ORCHESTRATOR,
    ROLE_REVIEWER,
    detect_role,
)

_FINDING_ID = re.compile(r"\[([^\]\s]+#\d+)\]")


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
