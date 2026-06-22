"""The labeled dataset — hand-judged cases paired with a human gold outcome.

Meta-evaluation measures a *judge* against ground truth, so its ground truth cannot come
from a model: each :class:`LabeledCase` carries a ``gold`` :class:`Outcome` set by a human,
defensible independent of any judge. The runner then asks both ATF and the single-judge
baseline to rule on the same case and scores each ruling against ``gold``.

The on-disk format is plain JSON (stdlib ``json`` only — no schema library), one object per
entry, mirroring the golden-set format so the two read alike::

    {
      "id": "sql-wrong-question",
      "input": "...",
      "output": "...",
      "expectation": "...",
      "criteria": ["...", "..."],
      "gold": "fail"
    }

``output`` and ``criteria`` are optional; ``gold`` is required and must be ``"pass"`` or
``"fail"`` (the binary the meta-eval scores against). The gold id is mirrored into
``case.metadata["labeled_id"]`` so it survives a round-trip through the pipeline — the same
convention the golden set uses for ``golden_id``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..core.case import Case
from ..core.types import Outcome, outcome_from_str

# Meta-eval is a binary judgement problem: a human label is PASS or FAIL, never the
# tribunal's third "inconclusive" state. Restricting the gold vocabulary here keeps the
# agreement math (confusion matrix, kappa, fail-class precision/recall) a clean 2x2.
_GOLD_OUTCOMES = (Outcome.PASS, Outcome.FAIL)
_GOLD_VALUES = tuple(o.value for o in _GOLD_OUTCOMES)


@dataclass(frozen=True)
class LabeledCase:
    """One hand-labeled entry: the :class:`Case` to judge plus its human gold outcome.

    ``case_id`` is the stable identifier the report keys on (mirrored into
    ``case.metadata["labeled_id"]``). ``gold`` is the human ground-truth :class:`Outcome`
    (PASS or FAIL) every judge is scored against.
    """

    case_id: str
    case: Case
    gold: Outcome


def _to_case(entry: dict[str, object], case_id: str) -> Case:
    raw_criteria = entry.get("criteria", [])
    criteria = [str(c) for c in raw_criteria] if isinstance(raw_criteria, list) else []
    raw_output = entry.get("output")
    return Case(
        input=str(entry.get("input", "")),
        expectation=str(entry.get("expectation", "")),
        output=str(raw_output) if raw_output is not None else None,
        criteria=criteria,
        metadata={"labeled_id": case_id},
    )


def _gold_outcome(entry: dict[str, object], index: int) -> Outcome:
    if "gold" not in entry:
        raise ValueError(f"labeled entry {index}: missing required 'gold'")
    value = str(entry["gold"]).strip().lower()
    if value not in _GOLD_VALUES:
        raise ValueError(
            f"labeled entry {index}: unknown gold {value!r} "
            f"(expected one of {sorted(_GOLD_VALUES)})"
        )
    return outcome_from_str(value)


def load_labeled(path: str | Path) -> list[LabeledCase]:
    """Load a labeled-dataset JSON file into a list of :class:`LabeledCase`.

    The file may be either a top-level JSON array of entries or an object with a ``"cases"``
    array (so a dataset can grow a header later without breaking the loader). An entry
    without an ``id`` is keyed positionally (``case-0``, ``case-1``, …). A missing or unknown
    ``gold`` raises :class:`ValueError` — meta-eval is meaningless without ground truth, so a
    bad label fails loudly rather than silently defaulting.
    """

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw["cases"] if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise ValueError("labeled set must be a JSON array (or an object with a 'cases' array)")
    labeled: list[LabeledCase] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"labeled entry {index} is not a JSON object")
        case_id = str(entry.get("id") or f"case-{index}")
        labeled.append(LabeledCase(case_id, _to_case(entry, case_id), _gold_outcome(entry, index)))
    return labeled


def labeled_to_dicts(labeled: list[LabeledCase]) -> list[dict[str, object]]:
    """Serialize labeled cases back to the on-disk JSON shape (round-trips ``load_labeled``)."""

    out: list[dict[str, object]] = []
    for lc in labeled:
        entry: dict[str, object] = {
            "id": lc.case_id,
            "input": lc.case.input,
            "expectation": lc.case.expectation,
            "criteria": list(lc.case.criteria),
            "gold": lc.gold.value,
        }
        if lc.case.output is not None:
            entry["output"] = lc.case.output
        out.append(entry)
    return out


def save_labeled(path: str | Path, labeled: list[LabeledCase]) -> None:
    """Write ``labeled`` to ``path`` as pretty-printed JSON (the format ``load_labeled`` reads)."""

    payload = labeled_to_dicts(labeled)
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
