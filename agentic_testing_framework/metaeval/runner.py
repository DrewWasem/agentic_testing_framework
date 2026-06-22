"""Run a labeled dataset through both judges and score each against the human gold labels.

This is the meta-evaluation: for every :class:`LabeledCase` we collect the full ATF
tribunal's verdict AND the single-judge baseline's verdict, map each to a binary PASS/FAIL,
and compare both to the human ``gold``. The output is a :class:`MetaEvalReport` carrying, for
each judge, the agreement bundle (raw agreement, Cohen's kappa, fail-class precision/recall/
F1) plus the per-case rows the numbers were computed from — so the comparison is auditable,
not just a pair of scores.

**Binary mapping (documented contract).** A judge's ruling is mapped to the gold vocabulary
by ``PASS → pass`` and *anything else → fail* — so the tribunal's third state,
``inconclusive``, counts as FAIL. The rationale: gold labels are binary (a human said the
output is good or it is not), and an evaluator that cannot commit to PASS has not certified
the output as good. Folding ``inconclusive`` into FAIL is the conservative choice and keeps
the agreement math a clean 2x2. The mapping lives in :func:`_to_binary`, one place.

All scoring is delegated to :mod:`agreement` (stdlib only); nothing here — and nothing in
``orchestrator.py`` — averages. The ATF pipeline is duck-typed (anything with
``run_case(case) -> Verdict``), so the runner stays decoupled from the concrete pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from ..core.case import Case
from ..core.types import Outcome, Verdict
from ..providers.base import Provider
from .agreement import Pair, cohens_kappa, confusion_matrix, precision_recall, raw_agreement
from .baseline import single_judge
from .dataset import LabeledCase


class _Pipeline(Protocol):
    """The single method the meta-eval runner needs from an ATF pipeline."""

    def run_case(self, case: Case) -> Verdict: ...


def _to_binary(outcome: Outcome) -> Outcome:
    """Map any verdict onto the binary gold vocabulary: PASS stays PASS, everything else FAIL.

    ``inconclusive`` becomes FAIL on purpose — see the module docstring. One place so both
    judges and every metric share the exact same mapping.
    """

    return Outcome.PASS if outcome is Outcome.PASS else Outcome.FAIL


@dataclass(frozen=True)
class JudgeScores:
    """One judge's agreement with the gold labels: raw %, kappa, and fail-class P/R/F1.

    ``agreements`` is the count of cases where the judge matched gold (``agreements``/``total``
    is :attr:`raw_agreement`). ``fail_precision``/``fail_recall``/``fail_f1`` score the *fail*
    class — catching bad output is the high-value job a lenient judge fails at. ``confusion``
    is the dense 2x2 ``{(gold, predicted): count}`` the numbers were derived from.
    """

    label: str
    raw_agreement: float
    cohens_kappa: float
    fail_precision: float
    fail_recall: float
    fail_f1: float
    agreements: int
    total: int
    confusion: dict[tuple[Outcome, Outcome], int]


def _score_judge(label: str, pairs: list[Pair]) -> JudgeScores:
    precision, recall, f1 = precision_recall(pairs, Outcome.FAIL)
    agreements = sum(1 for gold, pred in pairs if gold is pred)
    return JudgeScores(
        label=label,
        raw_agreement=raw_agreement(pairs),
        cohens_kappa=cohens_kappa(pairs),
        fail_precision=precision,
        fail_recall=recall,
        fail_f1=f1,
        agreements=agreements,
        total=len(pairs),
        confusion=confusion_matrix(pairs),
    )


@dataclass(frozen=True)
class CaseRow:
    """One case's gold label and what each judge ruled (already mapped to binary).

    ``atf_correct``/``baseline_correct`` are the per-row hits the report tallies — the audit
    trail behind the headline agreement counts.
    """

    case_id: str
    gold: Outcome
    atf: Outcome
    baseline: Outcome

    @property
    def atf_correct(self) -> bool:
        return self.atf is self.gold

    @property
    def baseline_correct(self) -> bool:
        return self.baseline is self.gold


@dataclass(frozen=True)
class MetaEvalReport:
    """The meta-evaluation result: both judges' score bundles plus the per-case rows.

    ``atf`` and ``baseline`` are :class:`JudgeScores` against the same gold labels; ``rows``
    is one :class:`CaseRow` per labeled case (``len(rows) == size``); ``size`` is the dataset
    size. Compare ``atf.cohens_kappa`` / ``atf.fail_recall`` against the baseline's to read
    whether structure beat the lenient single judge — honestly, on the numbers.
    """

    atf: JudgeScores
    baseline: JudgeScores
    rows: tuple[CaseRow, ...]
    size: int


def run_metaeval(
    labeled: Iterable[LabeledCase],
    *,
    atf_pipeline: _Pipeline,
    baseline_provider: Provider,
) -> MetaEvalReport:
    """Score the ATF tribunal and the single-judge baseline against the human gold labels.

    For each :class:`LabeledCase`: the ATF verdict is ``atf_pipeline.run_case(case).outcome``
    mapped to binary; the baseline is :func:`single_judge` (already binary). Both are paired
    with ``gold`` and scored by :mod:`agreement`. Returns a :class:`MetaEvalReport` with both
    judges' bundles populated and one row per case.
    """

    rows: list[CaseRow] = []
    atf_pairs: list[Pair] = []
    baseline_pairs: list[Pair] = []
    for lc in labeled:
        atf_outcome = _to_binary(atf_pipeline.run_case(lc.case).outcome)
        baseline_outcome = _to_binary(single_judge(lc.case, baseline_provider))
        rows.append(CaseRow(lc.case_id, lc.gold, atf_outcome, baseline_outcome))
        atf_pairs.append((lc.gold, atf_outcome))
        baseline_pairs.append((lc.gold, baseline_outcome))
    return MetaEvalReport(
        atf=_score_judge("ATF tribunal", atf_pairs),
        baseline=_score_judge("Single-judge baseline", baseline_pairs),
        rows=tuple(rows),
        size=len(rows),
    )


def _verdict_word(correct: bool) -> str:
    return "correct" if correct else "WRONG"


def render_markdown(report: MetaEvalReport) -> str:
    """Render the report as Markdown: a comparison table, per-case rows, and an honest verdict.

    The verdict line is deliberately plain — "ATF agreed with X/N vs baseline Y/N" — so the
    committed RESULTS file states the result without spin. If ATF did not win, this says so.
    """

    atf, base = report.atf, report.baseline
    lines: list[str] = []
    lines.append("# Meta-evaluation: ATF tribunal vs. single-judge baseline")
    lines.append("")
    lines.append(
        f"Scored {report.size} hand-labeled case(s); each judge's PASS/FAIL ruling compared "
        "to the human gold label. Higher is better across the board: Cohen's kappa corrects "
        "for chance agreement, and fail-recall is the fraction of genuinely-bad outputs the "
        "judge caught (the high-value job)."
    )
    lines.append("")
    lines.append("| Judge | Agreement | Cohen's kappa | Fail precision | Fail recall | Fail F1 |")
    lines.append("| ----- | --------- | ------------- | -------------- | ----------- | ------- |")
    for s in (atf, base):
        lines.append(
            f"| {s.label} "
            f"| {s.raw_agreement:.3f} ({s.agreements}/{s.total}) "
            f"| {s.cohens_kappa:.3f} "
            f"| {s.fail_precision:.3f} "
            f"| {s.fail_recall:.3f} "
            f"| {s.fail_f1:.3f} |"
        )
    lines.append("")
    lines.append("## Per-case rulings")
    lines.append("")
    lines.append("| Case | Gold | ATF | Baseline |")
    lines.append("| ---- | ---- | --- | -------- |")
    for row in report.rows:
        atf_cell = f"{row.atf.value} ({_verdict_word(row.atf_correct)})"
        base_cell = f"{row.baseline.value} ({_verdict_word(row.baseline_correct)})"
        lines.append(f"| {row.case_id} | {row.gold.value} | {atf_cell} | {base_cell} |")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(
        f"ATF agreed with {atf.agreements}/{atf.total} gold labels "
        f"(kappa {atf.cohens_kappa:.3f}, fail-recall {atf.fail_recall:.3f}) "
        f"vs baseline {base.agreements}/{base.total} "
        f"(kappa {base.cohens_kappa:.3f}, fail-recall {base.fail_recall:.3f})."
    )
    lines.append("")
    return "\n".join(lines)
