"""The evidence ledger — one append-only record of every finding in a case.

This is the spine of the framework's auditability: every check and reviewer writes here,
and the orchestrator rules from here. ``summary_facts`` renders the deterministic findings
as the grounding block injected into reviewer prompts.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .finding import Finding
from .types import Severity


class EvidenceLedger:
    """Append-only collection of :class:`Finding`, with id assignment and queries."""

    def __init__(self) -> None:
        self._findings: list[Finding] = []

    def add(self, finding: Finding) -> Finding:
        """Append a finding, assigning it a stable id, and return the stored copy."""

        stored = finding.with_id(f"{finding.source}#{len(self._findings)}")
        self._findings.append(stored)
        return stored

    def extend(self, findings: Iterable[Finding]) -> list[Finding]:
        return [self.add(f) for f in findings]

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(self._findings)

    def __len__(self) -> int:
        return len(self._findings)

    def _matches(self, finding: Finding, sources: Sequence[str]) -> bool:
        return any(finding.source == s or finding.source.startswith(f"{s}:") for s in sources)

    def by_source(self, *sources: str) -> list[Finding]:
        """Findings whose source equals or is prefixed by any of ``sources``."""

        return [f for f in self._findings if self._matches(f, sources)]

    def by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self._findings if f.severity == severity]

    def failures(self) -> list[Finding]:
        return [f for f in self._findings if f.passed is False]

    def gate_failures(self) -> list[Finding]:
        """Failed findings flagged as hard gates — these short-circuit the case."""

        return [f for f in self._findings if bool(f.metadata.get("gate")) and f.passed is False]

    def summary_facts(self, sources: Sequence[str] = ("clerk",)) -> str:
        """Render selected findings as a plain-text block for prompt grounding.

        Defaults to the deterministic (clerk) findings — the hard facts a reviewer must
        treat as ground truth rather than recompute.
        """

        lines: list[str] = []
        for f in self._findings:
            if not self._matches(f, sources):
                continue
            status = "" if f.passed is None else ("/PASS" if f.passed else "/FAIL")
            head = f"- [{f.id}] ({f.severity.value}{status}) {f.message}"
            if f.evidence:
                head += f" | evidence: {f.evidence!r}"
            lines.append(head)
        return "\n".join(lines) if lines else "(no deterministic findings)"
