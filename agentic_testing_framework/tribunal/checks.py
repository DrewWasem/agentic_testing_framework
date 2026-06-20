"""Deterministic checks — the Clerk's tools.

These run first and for free. They establish hard facts (counts, lengths, URL validity)
that ground every downstream reviewer. Any check can be flagged as a hard ``gate``:
a failed gate short-circuits the case before a single token is spent.

Severity convention: a failed gate is HIGH; a failed non-gate constraint is MEDIUM (it is
still real evidence the orchestrator should weigh); anything informational is INFO.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

from ..core.case import Case
from ..core.finding import Finding
from ..core.types import Severity


@runtime_checkable
class Check(Protocol):
    """A deterministic check: given a case, emit zero or more findings."""

    name: str

    def run(self, case: Case) -> list[Finding]: ...


def _severity_for(passed: bool | None, gate: bool) -> Severity:
    if passed is False:
        return Severity.HIGH if gate else Severity.MEDIUM
    return Severity.INFO


class WordCountCheck:
    """Report the output's word count; optionally gate on a min/max bound."""

    name = "word_count"

    def __init__(
        self,
        *,
        min_words: int | None = None,
        max_words: int | None = None,
        gate: bool = False,
    ) -> None:
        self.min_words = min_words
        self.max_words = max_words
        self.gate = gate

    def run(self, case: Case) -> list[Finding]:
        count = len((case.output or "").split())
        passed: bool | None = None
        if self.min_words is not None or self.max_words is not None:
            passed = True
            if self.min_words is not None and count < self.min_words:
                passed = False
            if self.max_words is not None and count > self.max_words:
                passed = False
        bounds = []
        if self.min_words is not None:
            bounds.append(f"min {self.min_words}")
        if self.max_words is not None:
            bounds.append(f"max {self.max_words}")
        suffix = f" (bounds: {', '.join(bounds)})" if bounds else ""
        return [
            Finding(
                source="clerk:word_count",
                severity=_severity_for(passed, self.gate),
                message=f"Output word count = {count}{suffix}.",
                passed=passed,
                metadata={"gate": self.gate, "count": count},
            )
        ]


class SentenceLengthCheck:
    """Report the average sentence length; optionally gate on a maximum average."""

    name = "sentence_length"
    _SPLIT = re.compile(r"[.!?]+")

    def __init__(self, *, max_avg_words: float | None = None, gate: bool = False) -> None:
        self.max_avg_words = max_avg_words
        self.gate = gate

    def run(self, case: Case) -> list[Finding]:
        text = case.output or ""
        sentences = [s for s in self._SPLIT.split(text) if s.strip()]
        word_total = len(text.split())
        avg = word_total / len(sentences) if sentences else float(word_total)
        passed: bool | None = None
        if self.max_avg_words is not None:
            passed = avg <= self.max_avg_words
        return [
            Finding(
                source="clerk:sentence_length",
                severity=_severity_for(passed, self.gate),
                message=(
                    f"Average sentence length = {avg:.1f} words "
                    f"across {len(sentences)} sentence(s)."
                ),
                passed=passed,
                metadata={"gate": self.gate, "avg_words": avg, "sentences": len(sentences)},
            )
        ]


class URLValidityCheck:
    """Validate any URLs in the output; optionally gate on malformed URLs."""

    name = "url_validity"
    _URL = re.compile(r"https?://[^\s)>\]}\"']+")

    def __init__(self, *, gate: bool = False, require_https: bool = False) -> None:
        self.gate = gate
        self.require_https = require_https

    def run(self, case: Case) -> list[Finding]:
        # Trailing sentence punctuation is not part of the URL.
        urls = [u.rstrip(".,;:!?") for u in self._URL.findall(case.output or "")]
        if not urls:
            return [
                Finding(
                    source="clerk:url_validity",
                    severity=Severity.INFO,
                    message="No URLs found in output.",
                    metadata={"gate": self.gate, "urls": 0, "malformed": 0},
                )
            ]
        malformed: list[str] = []
        for url in urls:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                malformed.append(url)
            elif self.require_https and parsed.scheme != "https":
                malformed.append(url)
        passed = not malformed
        return [
            Finding(
                source="clerk:url_validity",
                severity=_severity_for(passed, self.gate),
                message=f"Found {len(urls)} URL(s); {len(malformed)} malformed.",
                evidence=", ".join(malformed),
                passed=passed,
                metadata={"gate": self.gate, "urls": len(urls), "malformed": len(malformed)},
            )
        ]


def default_checks() -> list[Check]:
    """The baseline check set: word count, sentence length, URL validity (none gating)."""

    return [WordCountCheck(), SentenceLengthCheck(), URLValidityCheck()]
