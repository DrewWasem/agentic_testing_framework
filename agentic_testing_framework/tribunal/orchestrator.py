"""The orchestrator — adjudicates the evidence ledger into a final verdict.

It does NOT average scores or take a majority vote: it finds where reviewers disagree,
weighs whose evidence is stronger, and rules, citing the finding ids that drove the
decision. On unparseable output it rules ``inconclusive`` rather than guessing.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.case import Case
from ..core.finding import Finding
from ..core.ledger import EvidenceLedger
from ..core.llm import complete_json
from ..core.parsing import JSONParseError
from ..core.roles import ROLE_ORCHESTRATOR, role_header
from ..core.types import Outcome, Verdict, outcome_from_str
from ..providers.base import Provider

ORCHESTRATOR_SYSTEM = (
    "You are the presiding orchestrator of an evaluation tribunal. You ADJUDICATE the "
    "evidence ledger -- you do NOT average scores or take a majority vote. Find where the "
    "reviewers disagree, weigh whose EVIDENCE is stronger, and rule. A single "
    "well-evidenced finding can outweigh several weakly-supported ones. Cite the finding "
    "ids that drive your ruling. Base your ruling ONLY on the provided findings; if the "
    'evidence is genuinely insufficient to decide, rule "inconclusive". '
    "Respond with ONLY a JSON object of the form: "
    '{"outcome": "pass|fail|inconclusive", "rationale": str, "cited_findings": [str]}.'
)


class Orchestrator:
    def __init__(self, provider: Provider, *, max_retries: int = 1) -> None:
        self._provider = provider
        self._max_retries = max_retries

    def adjudicate(self, case: Case, ledger: EvidenceLedger) -> Verdict:
        system = f"{role_header(ROLE_ORCHESTRATOR)}\n{ORCHESTRATOR_SYSTEM}"
        prompt = self._render_prompt(case, ledger.findings)
        try:
            data = complete_json(self._provider, system, prompt, max_retries=self._max_retries)
        except JSONParseError as exc:
            return Verdict(
                outcome=Outcome.INCONCLUSIVE,
                rationale=f"Orchestrator output could not be parsed as JSON: {exc}",
                findings=ledger.findings,
            )
        # Only accept citations that actually exist in the ledger — a hallucinated id
        # must not make it into a "traceable" verdict.
        valid_ids = {f.id for f in ledger.findings}
        cited_raw = data.get("cited_findings", [])
        cited = (
            tuple(str(x) for x in cited_raw if str(x) in valid_ids)
            if isinstance(cited_raw, list)
            else ()
        )
        return Verdict(
            outcome=outcome_from_str(str(data.get("outcome", "inconclusive"))),
            rationale=str(data.get("rationale", "")),
            cited_findings=cited,
            findings=ledger.findings,
        )

    def _render_prompt(self, case: Case, findings: Sequence[Finding]) -> str:
        lines = []
        for f in findings:
            status = "" if f.passed is None else (" PASS" if f.passed else " FAIL")
            line = f"[{f.id}] {f.source} ({f.severity.value}{status}): {f.message}"
            if f.evidence:
                line += f" | evidence: {f.evidence!r}"
            lines.append(line)
        ledger_text = "\n".join(lines) if lines else "(no findings)"
        return (
            f"TASK INPUT:\n{case.input}\n\n"
            f"EXPECTATION:\n{case.expectation}\n\n"
            f"EVIDENCE LEDGER:\n{ledger_text}\n"
        )
