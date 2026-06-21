"""The grounded reviewer — walks the criteria step by step, grounded by the clerk.

It grades only against the stated expectation/criteria, quotes evidence, and treats the
clerk's deterministic facts as ground truth. On unparseable model output it degrades to
a single failing "parse error" finding rather than crashing the case.
"""

from __future__ import annotations

from ..core.case import Case
from ..core.finding import Finding
from ..core.ledger import EvidenceLedger
from ..core.llm import complete_json
from ..core.parsing import JSONParseError
from ..core.roles import ROLE_REVIEWER, role_header
from ..core.types import Severity
from ..prompts import get_prompt
from ..providers.base import Provider
from ._judging import parse_findings

# Prompt-as-code: the reviewer's system text is versioned in the registry. ``PROMPT_ID`` is
# the key the pipeline stamps onto the verdict; ``REVIEWER_SYSTEM`` stays as a module-level
# alias of the registered text (byte-for-byte what it was) for any other importer.
PROMPT_ID = "reviewer"
REVIEWER_SYSTEM = get_prompt(PROMPT_ID).text


class Reviewer:
    def __init__(self, provider: Provider, *, max_retries: int = 1) -> None:
        self._provider = provider
        self._max_retries = max_retries

    def review(self, case: Case, ledger: EvidenceLedger) -> list[Finding]:
        system = f"{role_header(ROLE_REVIEWER)}\n{REVIEWER_SYSTEM}"
        prompt = self._render_prompt(case, ledger.summary_facts(("clerk",)))
        try:
            data = complete_json(self._provider, system, prompt, max_retries=self._max_retries)
        except JSONParseError as exc:
            return ledger.extend([self._parse_error(exc)])
        return ledger.extend(parse_findings(data.get("findings"), "reviewer"))

    def _render_prompt(self, case: Case, facts: str) -> str:
        if case.criteria:
            criteria = "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(case.criteria))
        else:
            criteria = "  (none provided -- grade against the expectation as a whole)"
        return (
            f"TASK INPUT:\n{case.input}\n\n"
            f"EXPECTATION:\n{case.expectation}\n\n"
            f"CRITERIA:\n{criteria}\n\n"
            f"AGENT OUTPUT:\n{case.output or '(empty output)'}\n\n"
            "DETERMINISTIC FACTS (already established -- treat as ground truth, do not "
            f"recompute):\n{facts}\n"
        )

    @staticmethod
    def _parse_error(exc: JSONParseError) -> Finding:
        return Finding(
            source="reviewer",
            severity=Severity.MEDIUM,
            message=f"Reviewer output could not be parsed as JSON: {exc}",
            passed=False,
            criterion="(parsing)",
        )
