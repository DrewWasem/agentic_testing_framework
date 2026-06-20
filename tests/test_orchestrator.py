"""The orchestrator: adjudicates (never averages), cites findings, degrades safely."""

import json

from agentic_testing_framework import Case, EvidenceLedger, Finding, MockProvider, Orchestrator
from agentic_testing_framework.core.types import Outcome, Severity


def test_orchestrator_adjudicates_rather_than_averages():
    # Three weak FAIL findings vs. one strongly-evidenced PASS. A majority vote or average
    # would FAIL; adjudication can let the minority-but-stronger finding win.
    ledger = EvidenceLedger()
    for i in range(3):
        ledger.add(
            Finding(
                source=f"council:l{i}", severity=Severity.LOW, message="weak doubt", passed=False
            )
        )
    strong = ledger.add(
        Finding(
            source="reviewer",
            severity=Severity.HIGH,
            message="decisive correctness",
            evidence="proof",
            passed=True,
        )
    )
    scripted = json.dumps(
        {
            "outcome": "pass",
            "rationale": "The high-severity, well-evidenced finding outweighs three weak doubts.",
            "cited_findings": [strong.id],
        }
    )
    verdict = Orchestrator(MockProvider([scripted])).adjudicate(
        Case(input="q", expectation="exp", output="x"), ledger
    )
    assert verdict.outcome is Outcome.PASS
    assert strong.id in verdict.cited_findings


def test_orchestrator_inconclusive_on_unparseable():
    verdict = Orchestrator(MockProvider(["garbage", "more garbage"]), max_retries=1).adjudicate(
        Case(input="q", expectation="e"), EvidenceLedger()
    )
    assert verdict.outcome is Outcome.INCONCLUSIVE


def test_orchestrator_retries_then_parses():
    good = json.dumps({"outcome": "fail", "rationale": "r", "cited_findings": []})
    verdict = Orchestrator(MockProvider(["not json", good]), max_retries=1).adjudicate(
        Case(input="q", expectation="e"), EvidenceLedger()
    )
    assert verdict.outcome is Outcome.FAIL


def test_orchestrator_drops_hallucinated_citations():
    ledger = EvidenceLedger()
    real = ledger.add(Finding(source="reviewer", severity=Severity.HIGH, message="m", passed=False))
    scripted = json.dumps(
        {
            "outcome": "fail",
            "rationale": "r",
            "cited_findings": [real.id, "reviewer#999", "made-up#0"],
        }
    )
    verdict = Orchestrator(MockProvider([scripted])).adjudicate(
        Case(input="q", expectation="e"), ledger
    )
    assert verdict.cited_findings == (real.id,)  # only the real id survives


def test_orchestrator_source_has_no_averaging_logic():
    # The "never average" invariant, guarded structurally: a future statistics.mean or
    # vote-count would trip this. Tokens are chosen so the prompt prose ("average scores",
    # "majority vote") is NOT matched — only code-level averaging constructs.
    from pathlib import Path

    import agentic_testing_framework.tribunal.orchestrator as orchestrator_module

    source = Path(orchestrator_module.__file__).read_text(encoding="utf-8")
    banned = ["statistics", "mean(", "median(", "/ len(", "/len(", "Counter(", ".most_common("]
    hits = [token for token in banned if token in source]
    assert not hits, f"orchestrator gained averaging/vote constructs: {hits}"
