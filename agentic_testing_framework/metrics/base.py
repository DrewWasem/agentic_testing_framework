"""The shared base for the named LLM-judge metrics.

A metric is a lens-style reviewer, not a deterministic check: it asks a model to score the
agent's output along one axis (faithfulness, relevancy, toxicity, …) and writes the result
into the same evidence ledger every other tribunal stage uses. The numeric score lives in
``Finding.metadata`` so nothing flows downstream as a bare number — the auditability
invariant holds for metrics exactly as it does for the council.

Subclasses supply only a ``name``, a ``scale`` (the high end of the rubric, e.g. 5), a
``threshold`` on the normalized 0..1 score, an optional ``higher_is_worse`` flag (for the
inverse metrics — hallucination, toxicity — where a *high* model score means a *worse*
result), and the metric-specific ``instruction`` text. Everything else — the role-tagged
system prompt, the call/parse/normalize loop, the tolerant score coercion, and the
ledger-writing — is shared here.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any

from ..core.case import Case
from ..core.finding import Finding
from ..core.ledger import EvidenceLedger
from ..core.llm import complete_json
from ..core.parsing import JSONParseError
from ..core.roles import ROLE_METRIC, role_header
from ..core.types import Severity
from ..providers.base import Provider

# Same tolerance the council/reviewer use for ``passed`` — a model that answers in prose
# ("four out of five", "0.8") still yields a usable number instead of crashing the metric.
_WORD_NUMBERS = {
    "zero": 0.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
}


def _coerce_score(value: Any) -> float | None:
    """Interpret a model-supplied score robustly, mirroring ``_coerce_passed``.

    Accepts a number, a numeric string (``"4"``, ``"0.8"``, ``"4/5"``), or a spelled-out
    word (``"four"``). Returns ``None`` when no number can be recovered, so the caller can
    record a parse-error finding rather than inventing a score.
    """

    if isinstance(value, bool):  # bool is an int subclass — keep it out of the number path
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if not token:
            return None
        if token in _WORD_NUMBERS:
            return _WORD_NUMBERS[token]
        if "/" in token:  # "4/5" -> 4 (the numerator is the score; scale handles the rest)
            token = token.split("/", 1)[0].strip()
        try:
            return float(token)
        except ValueError:
            for word in token.replace("/", " ").split():
                if word in _WORD_NUMBERS:
                    return _WORD_NUMBERS[word]
                try:
                    return float(word)
                except ValueError:
                    continue
    return None


class Metric(ABC):
    """An LLM-judge metric that writes one structured :class:`Finding` per evaluation."""

    name: str = "metric"
    scale: float = 5.0
    threshold: float = 0.6
    higher_is_worse: bool = False

    @property
    @abstractmethod
    def instruction(self) -> str:
        """The metric-specific guidance injected into the system prompt."""

    def _system(self) -> str:
        """Role-tagged system prompt; the role extra carries the metric name for the mock."""

        return (
            f"{role_header(ROLE_METRIC, self.name)}\n"
            f"You are an evaluation metric named '{self.name}'. {self.instruction} "
            "Judge the agent OUTPUT only against the provided INPUT, EXPECTATION, and "
            "CRITERIA -- nothing else. Quote an exact span of evidence from the output. "
            f"Score on an integer scale from 1 (worst) to {int(self.scale)} (best). "
            "Respond with ONLY a JSON object of the form "
            '{"score": <number>, "reasoning": <str>, "evidence": <str>}. '
            "If you are unsure, say so in the reasoning and score conservatively. Do not "
            "guess or fabricate."
        )

    def _render_prompt(self, case: Case) -> str:
        if case.criteria:
            criteria = "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(case.criteria))
        else:
            criteria = "  (none provided -- judge against the expectation as a whole)"
        return (
            f"TASK INPUT:\n{case.input}\n\n"
            f"EXPECTATION:\n{case.expectation}\n\n"
            f"CRITERIA:\n{criteria}\n\n"
            f"AGENT OUTPUT:\n{case.output or '(empty output)'}\n\n"
            "Score the output as instructed and quote your evidence.\n"
        )

    def _normalize(self, raw_score: float) -> float:
        """Map a raw 1..scale score onto 0..1, inverting it for the 'higher is worse' metrics.

        A 1..scale rubric is normalized so 1 -> 0.0 and ``scale`` -> 1.0. For inverse metrics
        (hallucination, toxicity) a high raw score is *bad*, so the normalized score is
        flipped: a clean output scores near 1.0 regardless of which direction the rubric ran.
        """

        span = self.scale - 1.0
        clamped = max(1.0, min(self.scale, raw_score))
        fraction = (clamped - 1.0) / span if span > 0 else 1.0
        return round(1.0 - fraction if self.higher_is_worse else fraction, 4)

    def _build_finding(self, data: dict[str, Any]) -> Finding:
        raw = _coerce_score(data.get("score"))
        if raw is not None and not math.isfinite(raw):
            raw = None  # reject NaN/inf: a non-finite score must fail closed, never pass open
        reasoning = str(data.get("reasoning", "")).strip()
        evidence = str(data.get("evidence", "")).strip()
        if raw is None:
            return Finding(
                source=f"metric:{self.name}",
                severity=Severity.MEDIUM,
                message=f"{self.name}: no numeric score in model output -- {reasoning or 'n/a'}",
                evidence=evidence,
                passed=False,
                criterion=self.name,
                metadata={
                    "metric": self.name,
                    "score": None,
                    "raw_score": None,
                    "scale": self.scale,
                },
            )
        score = self._normalize(raw)
        passed = score >= self.threshold
        severity = Severity.INFO if passed else (Severity.HIGH if score < 0.4 else Severity.MEDIUM)
        message = (
            f"{self.name}: {int(raw) if raw.is_integer() else raw}/{int(self.scale)} "
            f"(normalized {score}) -- {reasoning or 'no reasoning given'}"
        )
        metadata: dict[str, Any] = {
            "metric": self.name,
            "score": score,
            "raw_score": raw,
            "scale": self.scale,
            "threshold": self.threshold,
        }
        self._augment_metadata(data, metadata)
        return Finding(
            source=f"metric:{self.name}",
            severity=severity,
            message=message,
            evidence=evidence,
            passed=passed,
            criterion=self.name,
            metadata=metadata,
        )

    def _augment_metadata(self, data: dict[str, Any], metadata: dict[str, Any]) -> None:  # noqa: B027
        """Hook for subclasses to stash extra fields (e.g. G-Eval's derived steps).

        Intentionally a no-op default, not abstract: only G-Eval overrides it, and forcing
        the other four metrics to declare an empty body would be pure ceremony.
        """

    def evaluate(self, case: Case, provider: Provider, ledger: EvidenceLedger) -> Finding:
        """Score ``case`` with ``provider`` and write the resulting finding into ``ledger``.

        On unparseable model output the metric degrades to a single failing finding (the
        same contract the reviewer and council follow) rather than raising.
        """

        try:
            data = complete_json(provider, self._system(), self._render_prompt(case))
        except JSONParseError as exc:
            return ledger.add(self._parse_error(exc))
        return ledger.add(self._build_finding(data))

    def _parse_error(self, exc: JSONParseError) -> Finding:
        return Finding(
            source=f"metric:{self.name}",
            severity=Severity.MEDIUM,
            message=f"{self.name} output could not be parsed as JSON: {exc}",
            passed=False,
            criterion=self.name,
            metadata={"metric": self.name, "score": None, "scale": self.scale},
        )
