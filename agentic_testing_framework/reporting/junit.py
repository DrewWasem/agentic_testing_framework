"""Render verdicts as JUnit XML so any CI runner can consume the tribunal's rulings.

One ``<testcase>`` per (name, verdict). A non-PASS outcome emits a ``<failure>`` whose
message is the orchestrator's rationale and whose body lists the cited findings, so the
failure a CI dashboard surfaces still points back at the evidence. A PASS is a bare
``<testcase>``. The suite carries ``tests`` and ``failures`` counts.

Standard library only: :mod:`xml.etree.ElementTree` builds the tree and escapes every
attribute and text node, so the output always parses (verified against
:func:`xml.dom.minidom.parseString`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, SubElement, tostring

from ..core.types import Outcome

if TYPE_CHECKING:
    from ..core.types import Verdict


def render_junit(
    results: Sequence[tuple[str, Verdict]],
    *,
    suite_name: str = "atf",
) -> str:
    """Render ``(name, verdict)`` pairs as a JUnit ``<testsuite>`` XML document.

    Args:
        results: one ``(testcase name, verdict)`` pair per case.
        suite_name: the ``name`` attribute on the ``<testsuite>``.

    Returns:
        A JUnit XML document as a string, parseable by ``xml.dom.minidom.parseString``.
    """

    failures = sum(1 for _name, verdict in results if verdict.outcome is not Outcome.PASS)
    suite = Element(
        "testsuite",
        {
            "name": suite_name,
            "tests": str(len(results)),
            "failures": str(failures),
            "errors": "0",
        },
    )
    for name, verdict in results:
        case = SubElement(suite, "testcase", {"name": name, "classname": suite_name})
        if verdict.outcome is not Outcome.PASS:
            failure = SubElement(
                case,
                "failure",
                {
                    "message": verdict.rationale or verdict.outcome.value,
                    "type": verdict.outcome.value,
                },
            )
            failure.text = _failure_body(verdict)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + tostring(suite, encoding="unicode")


def _failure_body(verdict: Verdict) -> str:
    """The text inside a ``<failure>``: the rationale plus the cited finding ids."""

    lines = [f"Outcome: {verdict.outcome.value}", f"Rationale: {verdict.rationale}"]
    if verdict.cited_findings:
        lines.append("Cited findings:")
        lines.extend(f"  - {fid}" for fid in verdict.cited_findings)
    else:
        lines.append("Cited findings: (none)")
    return "\n".join(lines)
