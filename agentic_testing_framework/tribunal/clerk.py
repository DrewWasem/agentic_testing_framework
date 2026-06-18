"""The Clerk — runs deterministic checks first and owns the hard-gate short-circuit.

Its findings are the ground truth injected into every reviewer prompt. If any gating
check fails, the case is decided here, before a single model is called.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..core.case import Case
from ..core.finding import Finding
from ..core.ledger import EvidenceLedger
from .checks import Check, default_checks


@dataclass(frozen=True)
class ClerkResult:
    gate_failed: bool
    gate_findings: tuple[Finding, ...]


class Clerk:
    def __init__(self, checks: Sequence[Check] | None = None) -> None:
        self._checks: list[Check] = list(checks) if checks is not None else default_checks()

    @property
    def checks(self) -> tuple[Check, ...]:
        return tuple(self._checks)

    def inspect(self, case: Case, ledger: EvidenceLedger) -> ClerkResult:
        for check in self._checks:
            for finding in check.run(case):
                ledger.add(finding)
        gate_findings = tuple(ledger.gate_failures())
        return ClerkResult(gate_failed=bool(gate_findings), gate_findings=gate_findings)
