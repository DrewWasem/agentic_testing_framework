"""The council — N reviewers with distinct lenses that are allowed to disagree.

Each lens writes its own findings into the ledger. The council never reconciles or
averages them; surfacing the disagreement is the point. Reconciliation is the
orchestrator's job.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.case import Case
from ..core.finding import Finding
from ..core.ledger import EvidenceLedger
from ..core.llm import complete_json
from ..core.parsing import JSONParseError
from ..core.roles import ROLE_COUNCIL, role_header
from ..core.types import Severity
from ..providers.base import Provider
from ._judging import parse_findings

LENS_GUIDANCE = {
    "accuracy": "Judge ONLY factual and logical correctness against the expectation.",
    "completeness": "Judge ONLY whether every required part of the task is present.",
    "clarity": "Judge ONLY clarity, structure, and readability.",
    "adversarial": "Act as a skeptic: hunt for the single strongest reason this output FAILS.",
}


class Council:
    DEFAULT_LENSES: tuple[str, ...] = ("accuracy", "completeness", "clarity", "adversarial")

    def __init__(
        self,
        provider: Provider,
        lenses: Sequence[str] | None = None,
        *,
        max_retries: int = 1,
    ) -> None:
        self._provider = provider
        self._lenses = tuple(lenses) if lenses is not None else self.DEFAULT_LENSES
        self._max_retries = max_retries

    @property
    def lenses(self) -> tuple[str, ...]:
        return self._lenses

    def deliberate(self, case: Case, ledger: EvidenceLedger) -> list[Finding]:
        facts = ledger.summary_facts(("clerk",))
        reviewer_notes = self._render_reviewer_notes(ledger.by_source("reviewer"))
        added: list[Finding] = []
        for lens in self._lenses:
            system = f"{role_header(ROLE_COUNCIL, lens)}\n{self._system(lens)}"
            prompt = self._render_prompt(case, lens, facts, reviewer_notes)
            try:
                data = complete_json(self._provider, system, prompt, max_retries=self._max_retries)
            except JSONParseError as exc:
                added.append(ledger.add(self._parse_error(lens, exc)))
                continue
            for finding in parse_findings(
                data.get("findings"), f"council:{lens}", extra_meta={"lens": lens}
            ):
                added.append(ledger.add(finding))
        return added

    def _system(self, lens: str) -> str:
        guidance = LENS_GUIDANCE.get(lens, f"Judge the output through the '{lens}' lens.")
        return (
            f"You are one reviewer on an evaluation council, assigned a single lens: "
            f"{lens}. {guidance} Judge the agent OUTPUT only against the EXPECTATION and "
            "CRITERIA, through your lens only. Treat the DETERMINISTIC FACTS as ground "
            "truth. Quote evidence. You may disagree with the other reviewers -- report "
            "what you see. Respond with ONLY a JSON object of the form: "
            '{"findings": [{"criterion": str, "passed": bool, '
            '"severity": "info|low|medium|high|critical", "message": str, '
            '"evidence": str}], "summary": str}. '
            "If unsure, say so and mark passed=false."
        )

    def _render_prompt(self, case: Case, lens: str, facts: str, reviewer_notes: str) -> str:
        if case.criteria:
            criteria = "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(case.criteria))
        else:
            criteria = "  (none provided -- grade against the expectation as a whole)"
        return (
            f"LENS: {lens}\n\n"
            f"TASK INPUT:\n{case.input}\n\n"
            f"EXPECTATION:\n{case.expectation}\n\n"
            f"CRITERIA:\n{criteria}\n\n"
            f"AGENT OUTPUT:\n{case.output or '(empty output)'}\n\n"
            f"DETERMINISTIC FACTS (ground truth):\n{facts}\n\n"
            f"PRIOR REVIEWER FINDINGS (for context, not authority):\n{reviewer_notes}\n"
        )

    @staticmethod
    def _render_reviewer_notes(findings: list[Finding]) -> str:
        if not findings:
            return "(reviewer recorded no findings)"
        lines = []
        for f in findings:
            tag = "PASS" if f.passed else "FAIL" if f.passed is False else "NOTE"
            lines.append(f"- [{f.id}] {tag}: {f.message}")
        return "\n".join(lines)

    @staticmethod
    def _parse_error(lens: str, exc: JSONParseError) -> Finding:
        return Finding(
            source=f"council:{lens}",
            severity=Severity.MEDIUM,
            message=f"Council lens '{lens}' output could not be parsed as JSON: {exc}",
            passed=False,
            metadata={"lens": lens},
        )
