"""The council: configurable lenses, and disagreement preserved (never collapsed)."""

import json

from agentic_testing_framework import Case, Council, EvidenceLedger, MockProvider


def test_lenses_are_configurable():
    assert Council(MockProvider(), lenses=["accuracy", "clarity"]).lenses == ("accuracy", "clarity")


def test_council_preserves_disagreement():
    pass_finding = json.dumps(
        {
            "findings": [
                {
                    "criterion": "c1",
                    "passed": True,
                    "severity": "info",
                    "message": "looks right",
                    "evidence": "e",
                }
            ],
            "summary": "ok",
        }
    )
    fail_finding = json.dumps(
        {
            "findings": [
                {
                    "criterion": "c1",
                    "passed": False,
                    "severity": "high",
                    "message": "actually wrong",
                    "evidence": "e",
                }
            ],
            "summary": "no",
        }
    )
    mock = MockProvider([pass_finding, fail_finding])
    ledger = EvidenceLedger()
    case = Case(input="q", expectation="exp", output="x", criteria=["c1"])
    Council(mock, lenses=["accuracy", "adversarial"]).deliberate(case, ledger)

    council_findings = ledger.by_source("council")
    assert any(f.passed is True for f in council_findings)
    assert any(f.passed is False for f in council_findings)  # both survive — not averaged
    assert {f.metadata["lens"] for f in council_findings} == {"accuracy", "adversarial"}
