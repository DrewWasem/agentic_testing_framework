"""Core data model: ledger, case, parsing, type coercion, metrics."""

import pytest

from agentic_testing_framework import (
    Case,
    EvidenceLedger,
    Finding,
    Outcome,
    Severity,
    Verdict,
    summarize,
)
from agentic_testing_framework.core.parsing import JSONParseError, extract_json
from agentic_testing_framework.core.types import outcome_from_str, severity_from_str


def test_ledger_assigns_ids_and_queries():
    ledger = EvidenceLedger()
    first = ledger.add(Finding(source="clerk:word_count", severity=Severity.INFO, message="m"))
    assert first.id == "clerk:word_count#0"
    ledger.add(Finding(source="reviewer", severity=Severity.HIGH, message="bad", passed=False))
    assert len(ledger) == 2
    assert len(ledger.by_source("clerk")) == 1
    assert len(ledger.failures()) == 1


def test_summary_facts_includes_only_clerk_by_default():
    ledger = EvidenceLedger()
    ledger.add(Finding(source="clerk:x", severity=Severity.INFO, message="hard-fact"))
    ledger.add(Finding(source="reviewer", severity=Severity.INFO, message="opinion"))
    facts = ledger.summary_facts()
    assert "hard-fact" in facts
    assert "opinion" not in facts


def test_gate_failures_filter():
    ledger = EvidenceLedger()
    ledger.add(
        Finding(
            source="clerk:a",
            severity=Severity.HIGH,
            message="g",
            passed=False,
            metadata={"gate": True},
        )
    )
    ledger.add(
        Finding(
            source="clerk:b",
            severity=Severity.INFO,
            message="ng",
            passed=False,
            metadata={"gate": False},
        )
    )
    assert len(ledger.gate_failures()) == 1


def test_case_normalizes_criteria_to_tuple():
    case = Case(input="i", expectation="e", criteria=["a", "b"])
    assert case.criteria == ("a", "b")


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('blah blah {"x": 2} trailing text') == {"x": 2}
    with pytest.raises(JSONParseError):
        extract_json("no json object here")
    with pytest.raises(JSONParseError):
        extract_json('{"broken": ')


def test_severity_and_outcome_coercion():
    assert severity_from_str("HIGH") is Severity.HIGH
    assert severity_from_str("bogus") is Severity.INFO
    assert Severity.CRITICAL.rank > Severity.LOW.rank
    assert outcome_from_str("pass") is Outcome.PASS
    assert outcome_from_str("???") is Outcome.INCONCLUSIVE


def test_metrics_summarize():
    verdicts = [
        Verdict(Outcome.PASS, "r"),
        Verdict(Outcome.FAIL, "r", gated=True),
        Verdict(Outcome.PASS, "r"),
    ]
    summary = summarize(verdicts)
    assert summary.total == 3
    assert summary.passed == 2
    assert summary.failed == 1
    assert summary.gated == 1
    assert abs(summary.pass_rate - 2 / 3) < 1e-9


def test_extract_json_skips_prose_braces_and_nonjson_fences():
    # A stray brace in prose must not defeat extraction (W2 regression).
    assert extract_json('Here is the result } and now {"a": 1} done') == {"a": 1}
    # A non-JSON fenced block before the real object must be skipped.
    assert extract_json('```python\nprint(1)\n```\n{"ok": true}') == {"ok": True}
