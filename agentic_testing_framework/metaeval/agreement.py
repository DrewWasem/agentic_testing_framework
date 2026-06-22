"""Inter-rater agreement math — pure standard library, no numpy/sklearn.

Meta-evaluation reduces to: how well does a judge's PASS/FAIL ruling agree with the human
gold label? This module is the scoring kernel. Everything operates on ``pairs`` — a list of
``(gold, predicted)`` :class:`Outcome` tuples — and returns plain floats, so it carries no
dependency and (crucially) keeps all aggregation OUT of ``orchestrator.py`` (a source-grep
test enforces that the orchestrator never averages; the averaging lives here instead).

Three views, in increasing strictness:

* :func:`raw_agreement` — the fraction of pairs that match. Intuitive, but inflated when one
  label dominates (a judge that always says PASS looks good on a mostly-PASS set).
* :func:`cohens_kappa` — agreement corrected for the agreement expected by chance. This is
  the headline number: κ=1 is perfect, κ=0 is chance-level, κ<0 is worse than chance.
* :func:`precision_recall` — precision/recall/F1 for one class. Meta-eval reports these on
  the *fail* class, because catching a bad output is the high-value job a lenient judge fails
  at: fail-recall is "of the genuinely-bad outputs, what fraction did the judge catch?".
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.types import Outcome

# A meta-eval pair is (human gold, judge prediction); both are PASS/FAIL outcomes.
Pair = tuple[Outcome, Outcome]


def confusion_matrix(pairs: Sequence[Pair]) -> dict[tuple[Outcome, Outcome], int]:
    """Count each ``(gold, predicted)`` combination.

    Returns a dense map over the four PASS/FAIL cells (each present, zero if unseen) so a
    caller never has to guard a missing key. ``matrix[(gold, pred)]`` is the count of pairs
    whose gold was ``gold`` and whose prediction was ``pred``.
    """

    matrix: dict[tuple[Outcome, Outcome], int] = {
        (gold, pred): 0
        for gold in (Outcome.PASS, Outcome.FAIL)
        for pred in (Outcome.PASS, Outcome.FAIL)
    }
    for gold, pred in pairs:
        matrix[(gold, pred)] = matrix.get((gold, pred), 0) + 1
    return matrix


def raw_agreement(pairs: Sequence[Pair]) -> float:
    """Fraction of pairs where the prediction equals the gold label (0.0 for an empty set)."""

    if not pairs:
        return 0.0
    matches = sum(1 for gold, pred in pairs if gold is pred)
    return matches / len(pairs)


def cohens_kappa(pairs: Sequence[Pair]) -> float:
    """Cohen's kappa: agreement corrected for chance, ``(p_o - p_e) / (1 - p_e)``.

    ``p_o`` is the observed agreement; ``p_e`` is the agreement expected if both raters
    labeled independently at their observed marginal rates. When ``1 - p_e == 0`` (both raters
    used a single label for every case, so chance agreement is already total) kappa is
    undefined by the formula; we return ``1.0`` if they nonetheless agreed everywhere and
    ``0.0`` otherwise, the standard degenerate-case convention.
    """

    n = len(pairs)
    if n == 0:
        return 0.0
    p_o = raw_agreement(pairs)

    labels = (Outcome.PASS, Outcome.FAIL)
    gold_counts = {label: sum(1 for g, _ in pairs if g is label) for label in labels}
    pred_counts = {label: sum(1 for _, p in pairs if p is label) for label in labels}
    p_e = sum((gold_counts[label] / n) * (pred_counts[label] / n) for label in labels)

    denom = 1.0 - p_e
    if denom == 0.0:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / denom


def precision_recall(
    pairs: Sequence[Pair], positive_label: Outcome = Outcome.FAIL
) -> tuple[float, float, float]:
    """Precision, recall, and F1 for ``positive_label`` (defaults to the *fail* class).

    With FAIL as positive: a true positive is a genuinely-bad output the judge caught,
    precision is "of the outputs the judge flagged, how many were truly bad", and recall is
    "of the truly-bad outputs, how many did the judge catch". Any of the three is ``0.0`` when
    its denominator is zero (no predicted positives → precision 0; no actual positives →
    recall 0), so the function never divides by zero.
    """

    tp = sum(1 for gold, pred in pairs if gold is positive_label and pred is positive_label)
    fp = sum(1 for gold, pred in pairs if gold is not positive_label and pred is positive_label)
    fn = sum(1 for gold, pred in pairs if gold is positive_label and pred is not positive_label)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1
