"""Shared helper: turn a model's JSON ``findings`` array into :class:`Finding` objects.

Used by both the reviewer and the council, which emit the same finding schema. Tolerant
of missing/oddly-typed fields so a slightly-off model response degrades to weaker
findings rather than crashing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.finding import Finding
from ..core.types import severity_from_str

_TRUE_TOKENS = {"true", "yes", "y", "1", "pass", "passed", "ok"}
_FALSE_TOKENS = {"false", "no", "n", "0", "fail", "failed"}


def _coerce_passed(value: Any) -> bool | None:
    """Interpret a model-supplied ``passed`` value robustly.

    Critically, a JSON *string* like ``"false"`` must NOT become ``True`` — which a naive
    ``bool(value)`` would do, silently inverting a failing finding into a passing one and
    corrupting the ledger the orchestrator rules from. Unknown values map to ``None``
    (no pass/fail recorded) rather than a falsely-passing ``True``.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
        return None
    return None


def parse_findings(
    items: Any,
    source: str,
    *,
    extra_meta: Mapping[str, Any] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(items, list):
        return findings
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_criterion = item.get("criterion")
        criterion = str(raw_criterion) if raw_criterion is not None else None
        findings.append(
            Finding(
                source=source,
                severity=severity_from_str(str(item.get("severity", "info"))),
                message=str(item.get("message", "")),
                evidence=str(item.get("evidence", "")),
                passed=_coerce_passed(item.get("passed")),
                criterion=criterion,
                metadata=dict(extra_meta) if extra_meta else {},
            )
        )
    return findings
