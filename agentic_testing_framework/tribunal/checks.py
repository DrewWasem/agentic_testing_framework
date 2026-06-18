"""Deterministic checks — the Clerk's tools.

These run first and for free. They establish hard facts (counts, lengths, URL validity,
forbidden/required patterns, JSON validity, numeric scores) that ground every downstream
reviewer. Any check can be flagged as a hard ``gate``: a failed gate short-circuits the
case before a single token is spent.

Severity convention: a failed gate is HIGH; a failed non-gate constraint is MEDIUM (it is
still real evidence the orchestrator should weigh); anything informational is INFO.

All pattern/score inputs are caller-supplied — the framework ships no domain-specific
block-list, rubric, or schema of its own.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
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


def _matches(pattern: str, text: str, *, regex: bool, ignore_case: bool) -> bool:
    if regex:
        return re.search(pattern, text, re.IGNORECASE if ignore_case else 0) is not None
    return (pattern.lower() in text.lower()) if ignore_case else (pattern in text)


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


class NonEmptyCheck:
    """Fail when the output is empty, whitespace-only, or below a minimum length.

    Pairs with the ``edge_case`` adversarial probe (empty input): a robust agent should
    still produce something.
    """

    name = "non_empty"

    def __init__(self, *, min_chars: int = 1, gate: bool = False) -> None:
        self.min_chars = min_chars
        self.gate = gate

    def run(self, case: Case) -> list[Finding]:
        text = (case.output or "").strip()
        passed = len(text) >= self.min_chars
        return [
            Finding(
                source="clerk:non_empty",
                severity=_severity_for(passed, self.gate),
                message=f"Output has {len(text)} non-whitespace char(s) (min {self.min_chars}).",
                passed=passed,
                metadata={"gate": self.gate, "chars": len(text)},
            )
        ]


class ForbiddenPatternCheck:
    """Fail when the output contains any forbidden substring or regex.

    Useful for safety canaries (an injection probe's expected leak token), banned phrasing,
    or refusal-bypass markers. Patterns are caller-supplied.
    """

    name = "forbidden_pattern"

    def __init__(
        self,
        patterns: Sequence[str],
        *,
        regex: bool = False,
        ignore_case: bool = True,
        gate: bool = False,
    ) -> None:
        self.patterns = tuple(patterns)
        self.regex = regex
        self.ignore_case = ignore_case
        if regex:
            for pattern in self.patterns:
                re.compile(pattern)  # surface a malformed pattern at construction, not mid-run
        self.gate = gate

    def run(self, case: Case) -> list[Finding]:
        text = case.output or ""
        hits = [
            p
            for p in self.patterns
            if _matches(p, text, regex=self.regex, ignore_case=self.ignore_case)
        ]
        passed = not hits
        return [
            Finding(
                source="clerk:forbidden_pattern",
                severity=_severity_for(passed, self.gate),
                message=f"{len(hits)} of {len(self.patterns)} forbidden pattern(s) present.",
                evidence=", ".join(hits),
                passed=passed,
                metadata={"gate": self.gate, "hits": list(hits)},
            )
        ]


class RequiredPatternCheck:
    """Fail when the output is missing any required substring or regex."""

    name = "required_pattern"

    def __init__(
        self,
        patterns: Sequence[str],
        *,
        regex: bool = False,
        ignore_case: bool = True,
        gate: bool = False,
    ) -> None:
        self.patterns = tuple(patterns)
        self.regex = regex
        self.ignore_case = ignore_case
        if regex:
            for pattern in self.patterns:
                re.compile(pattern)  # surface a malformed pattern at construction, not mid-run
        self.gate = gate

    def run(self, case: Case) -> list[Finding]:
        text = case.output or ""
        missing = [
            p
            for p in self.patterns
            if not _matches(p, text, regex=self.regex, ignore_case=self.ignore_case)
        ]
        passed = not missing
        return [
            Finding(
                source="clerk:required_pattern",
                severity=_severity_for(passed, self.gate),
                message=f"{len(missing)} of {len(self.patterns)} required pattern(s) missing.",
                evidence=", ".join(missing),
                passed=passed,
                metadata={"gate": self.gate, "missing": list(missing)},
            )
        ]


class JSONValidityCheck:
    """Fail when the output is not a valid JSON object, or is missing required keys."""

    name = "json_validity"

    def __init__(self, *, required_keys: Sequence[str] = (), gate: bool = False) -> None:
        self.required_keys = tuple(required_keys)
        self.gate = gate

    def run(self, case: Case) -> list[Finding]:
        text = (case.output or "").strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return [
                Finding(
                    source="clerk:json_validity",
                    severity=_severity_for(False, self.gate),
                    message="Output is not valid JSON.",
                    passed=False,
                    metadata={"gate": self.gate},
                )
            ]
        if not isinstance(parsed, dict):
            return [
                Finding(
                    source="clerk:json_validity",
                    severity=_severity_for(False, self.gate),
                    message=f"Output JSON is a {type(parsed).__name__}, not an object.",
                    passed=False,
                    metadata={"gate": self.gate},
                )
            ]
        missing = [k for k in self.required_keys if k not in parsed]
        passed = not missing
        return [
            Finding(
                source="clerk:json_validity",
                severity=_severity_for(passed, self.gate),
                message=f"Valid JSON object; {len(missing)} required key(s) missing.",
                evidence=", ".join(missing),
                passed=passed,
                metadata={"gate": self.gate, "missing": missing},
            )
        ]


class ScoreThresholdCheck:
    """Extract a numeric score from the output and gate on a minimum.

    Defaults to an ``N/M`` score (e.g. ``"8/10"`` -> 8). Supply a custom regex with one
    capture group to match other formats. If no score is found, the check fails — an agent
    that was asked to emit a score but didn't has not met the bar.
    """

    name = "score_threshold"
    # "N/M" where M is a common rating scale, so dates ("12/25/2026") and bare
    # fractions ("1/2") are not mistaken for scores.
    _DEFAULT = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(?:5|10|100)\b")

    def __init__(self, minimum: float, *, pattern: str | None = None, gate: bool = False) -> None:
        self.minimum = minimum
        self._pattern = re.compile(pattern) if pattern else self._DEFAULT
        if self._pattern.groups < 1:
            raise ValueError(
                "ScoreThresholdCheck pattern must contain one capture group for the score."
            )
        self.gate = gate

    def run(self, case: Case) -> list[Finding]:
        match = self._pattern.search(case.output or "")
        if match is None:
            return [
                Finding(
                    source="clerk:score_threshold",
                    severity=_severity_for(False, self.gate),
                    message=f"No numeric score found (expected >= {self.minimum}).",
                    passed=False,
                    metadata={"gate": self.gate, "score": None},
                )
            ]
        score = float(match.group(1))
        passed = score >= self.minimum
        return [
            Finding(
                source="clerk:score_threshold",
                severity=_severity_for(passed, self.gate),
                message=f"Extracted score {score} (threshold >= {self.minimum}).",
                evidence=match.group(0),
                passed=passed,
                metadata={"gate": self.gate, "score": score},
            )
        ]


def default_checks() -> list[Check]:
    """The baseline check set: word count, sentence length, URL validity (none gating)."""

    return [WordCountCheck(), SentenceLengthCheck(), URLValidityCheck()]
