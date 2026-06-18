"""The extended deterministic checks: patterns, non-empty, JSON validity, score threshold."""

import pytest

from agentic_testing_framework import (
    Case,
    ForbiddenPatternCheck,
    JSONValidityCheck,
    NonEmptyCheck,
    RequiredPatternCheck,
    ScoreThresholdCheck,
    Severity,
)


def _case(output):
    return Case(input="i", expectation="e", output=output)


def test_non_empty_check():
    assert NonEmptyCheck(gate=True).run(_case("   "))[0].passed is False
    assert NonEmptyCheck().run(_case("hello"))[0].passed is True


def test_forbidden_pattern_substring_and_regex():
    hit = ForbiddenPatternCheck(["OVERRIDDEN"], gate=True).run(_case("sure: overridden"))[0]
    assert hit.passed is False  # case-insensitive substring match
    assert hit.severity is Severity.HIGH
    assert "OVERRIDDEN" in hit.metadata["hits"]
    assert ForbiddenPatternCheck(["OVERRIDDEN"]).run(_case("a normal answer"))[0].passed is True
    rx = ForbiddenPatternCheck([r"\bSSN\b\s*\d"], regex=True).run(_case("SSN 123"))[0]
    assert rx.passed is False


def test_required_pattern_check():
    miss = RequiredPatternCheck(["Summary:", "Sources:"]).run(_case("Summary: ok"))[0]
    assert miss.passed is False
    assert "Sources:" in miss.metadata["missing"]
    assert RequiredPatternCheck(["Summary:"]).run(_case("Summary: ok"))[0].passed is True


def test_json_validity_check():
    assert JSONValidityCheck().run(_case('{"a": 1}'))[0].passed is True
    assert JSONValidityCheck().run(_case("not json"))[0].passed is False
    assert JSONValidityCheck().run(_case("[1, 2, 3]"))[0].passed is False  # not an object
    missing = JSONValidityCheck(required_keys=["a", "b"]).run(_case('{"a": 1}'))[0]
    assert missing.passed is False
    assert "b" in missing.metadata["missing"]


def test_score_threshold_check():
    assert ScoreThresholdCheck(7).run(_case("Clarity: 8/10 — good"))[0].passed is True
    fail = ScoreThresholdCheck(7).run(_case("Clarity: 5/10"))[0]
    assert fail.passed is False
    assert fail.metadata["score"] == 5.0
    no_score = ScoreThresholdCheck(7, gate=True).run(_case("no number here"))[0]
    assert no_score.passed is False  # a score was required, none found
    assert no_score.metadata["score"] is None
    custom = ScoreThresholdCheck(4, pattern=r"rating[:\s]+(\d+)").run(_case("rating: 4 stars"))[0]
    assert custom.passed is True


def test_score_threshold_ignores_dates_and_fractions():
    # the scale-aware default must not read a date or bare fraction as a score
    assert ScoreThresholdCheck(7, gate=True).run(_case("Due 12/25/2026"))[0].passed is False
    assert (
        ScoreThresholdCheck(7, gate=True).run(_case("about 1/2 done"))[0].metadata["score"] is None
    )
    assert ScoreThresholdCheck(7).run(_case("scored 92/100"))[0].passed is True


def test_score_threshold_rejects_pattern_without_capture_group():
    with pytest.raises(ValueError):
        ScoreThresholdCheck(5, pattern=r"\d+")
