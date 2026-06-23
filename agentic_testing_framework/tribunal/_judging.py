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


def _coerce_bool(value: Any) -> bool:
    """Interpret a model-supplied boolean flag (e.g. ``advisory``) robustly, defaulting False.

    Mirrors :func:`_coerce_passed`'s tolerance of loose values (``true``/``"yes"``/``1`` ...),
    but this is a plain flag, not a tri-state grade: an absent, unknown, or falsey value means
    "off" (``False``), never ``None``. A JSON *string* ``"false"`` must stay ``False`` rather
    than flipping on via a naive ``bool(value)``.
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_TOKENS
    return False


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
        # An advisory is a true observation BEYOND the stated expectation/criteria. It is
        # recorded and surfaced but must never count toward the verdict, so it is neither a
        # pass nor a fail of a stated criterion: force ``passed=None`` regardless of what the
        # model put in ``passed``.
        advisory = _coerce_bool(item.get("advisory"))
        passed = None if advisory else _coerce_passed(item.get("passed"))
        findings.append(
            Finding(
                source=source,
                severity=severity_from_str(str(item.get("severity", "info"))),
                message=str(item.get("message", "")),
                evidence=str(item.get("evidence", "")),
                passed=passed,
                criterion=criterion,
                metadata=dict(extra_meta) if extra_meta else {},
                advisory=advisory,
            )
        )
    return findings
