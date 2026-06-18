"""Deterministic checks and their edge cases."""

from agentic_testing_framework import (
    Case,
    SentenceLengthCheck,
    Severity,
    URLValidityCheck,
    WordCountCheck,
    default_checks,
)


def _case(output):
    return Case(input="i", expectation="e", output=output)


def test_word_count_reports_and_gates():
    finding = WordCountCheck(max_words=2, gate=True).run(_case("one two three"))[0]
    assert finding.passed is False
    assert finding.metadata["gate"] is True
    assert finding.severity is Severity.HIGH
    assert finding.metadata["count"] == 3


def test_word_count_empty_output_is_informational():
    finding = WordCountCheck().run(_case(None))[0]
    assert finding.metadata["count"] == 0
    assert finding.passed is None


def test_sentence_length_gate():
    finding = SentenceLengthCheck(max_avg_words=3, gate=True).run(
        _case("this sentence is quite long indeed.")
    )[0]
    assert finding.passed is False
    assert finding.severity is Severity.HIGH


def test_url_validity_flags_missing_netloc():
    finding = URLValidityCheck(gate=True).run(_case("good http://good.com bad http:///oops"))[0]
    assert finding.metadata["urls"] == 2
    assert finding.metadata["malformed"] == 1
    assert finding.passed is False
    assert finding.severity is Severity.HIGH


def test_url_validity_no_urls():
    finding = URLValidityCheck().run(_case("no links here at all"))[0]
    assert finding.metadata["urls"] == 0
    assert finding.passed is None


def test_url_validity_require_https():
    finding = URLValidityCheck(require_https=True).run(_case("http://insecure.example"))[0]
    assert finding.metadata["malformed"] == 1
    assert finding.passed is False


def test_default_checks_set():
    assert len(default_checks()) == 3
