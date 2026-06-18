"""The ``Finding`` — the single unit that flows through the evidence ledger.

Every deterministic check and every reviewer emits findings; nothing downstream sees a
bare pass/fail. A finding is immutable; the ledger assigns its id on append.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from .types import Severity


@dataclass(frozen=True)
class Finding:
    """A single piece of evidence.

    Attributes:
        source: where it came from, e.g. ``"clerk:word_count"``, ``"reviewer"``,
            ``"council:adversarial"``, ``"orchestrator"``.
        severity: how serious it is.
        message: human-readable description.
        evidence: the exact quoted span from the output that supports it.
        passed: pass/fail for criterion-style findings; ``None`` for purely informational ones.
        criterion: the criterion this finding grades, if any.
        id: assigned by the ledger on append (``"<source>#<n>"``).
        metadata: free-form structured extras (e.g. ``{"gate": True, "count": 42}``).
    """

    source: str
    severity: Severity
    message: str
    evidence: str = ""
    passed: bool | None = None
    criterion: str | None = None
    id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def with_id(self, finding_id: str) -> Finding:
        """Return a copy with ``id`` set (used by the ledger on append)."""

        return replace(self, id=finding_id)
