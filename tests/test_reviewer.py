"""The grounded reviewer: clerk facts injected, strict grading, graceful degradation."""

import json

from agentic_testing_framework import (
    Case,
    Clerk,
    EvidenceLedger,
    MockProvider,
    Reviewer,
    WordCountCheck,
)


def test_reviewer_prompt_is_grounded_by_clerk_facts():
    captured = {}

    def handler(system, prompt):
        captured["prompt"] = prompt
        return json.dumps({"findings": [], "summary": "ok"})

    ledger = EvidenceLedger()
    case = Case(input="q", expectation="exp", output="hello world", criteria=["c1"])
    Clerk([WordCountCheck()]).inspect(case, ledger)
    Reviewer(MockProvider(handler=handler)).review(case, ledger)
    assert "DETERMINISTIC FACTS" in captured["prompt"]
    assert "word count = 2" in captured["prompt"]  # the clerk's hard fact, injected


def test_reviewer_is_strict_on_known_bad_output():
    scripted = json.dumps(
        {
            "findings": [
                {
                    "criterion": "c1",
                    "passed": False,
                    "severity": "high",
                    "message": "criterion not met",
                    "evidence": "the output omits it",
                }
            ],
            "summary": "fail",
        }
    )
    ledger = EvidenceLedger()
    findings = Reviewer(MockProvider([scripted])).review(
        Case(input="q", expectation="exp", output="bad", criteria=["c1"]), ledger
    )
    assert len(findings) == 1
    assert findings[0].passed is False
    assert findings[0].severity.value == "high"
    assert findings[0].source == "reviewer"


def test_reviewer_degrades_on_unparseable_output():
    mock = MockProvider(["not json at all", "still not json"])
    ledger = EvidenceLedger()
    findings = Reviewer(mock, max_retries=1).review(
        Case(input="q", expectation="exp", output="x"), ledger
    )
    assert len(findings) == 1
    assert findings[0].passed is False
    assert "could not be parsed" in findings[0].message


def test_reviewer_treats_string_false_as_failure():
    # A model emitting the JSON *string* "false" must not be read as passing (B1 regression).
    scripted = json.dumps(
        {
            "findings": [
                {
                    "criterion": "c1",
                    "passed": "false",
                    "severity": "high",
                    "message": "no",
                    "evidence": "e",
                }
            ],
            "summary": "x",
        }
    )
    ledger = EvidenceLedger()
    findings = Reviewer(MockProvider([scripted])).review(
        Case(input="q", expectation="e", output="o", criteria=["c1"]), ledger
    )
    assert findings[0].passed is False
