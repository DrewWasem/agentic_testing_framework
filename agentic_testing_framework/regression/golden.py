"""The golden set — a JSON baseline of cases and their expected verdict outcomes.

A golden set is the regression contract: a small, version-controlled list of cases, each
carrying the input/output/expectation that defines it AND the outcome the tribunal is
*expected* to reach. Re-running it after a prompt edit or a model swap and diffing the new
outcomes against this baseline is how drift is caught.

The on-disk format is plain JSON (stdlib ``json`` only — no schema library), one object per
entry::

    {
      "id": "sql-revenue",
      "input": "...",
      "output": "...",
      "expectation": "...",
      "criteria": ["...", "..."],
      "expected": {"outcome": "pass"}
    }

``output`` and ``criteria`` are optional. ``expected.outcome`` is compared as a property
against the verdict's ``Outcome`` — never as a string against the rationale, which is free
prose and would make the baseline brittle.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..core.case import Case
from ..core.types import Outcome, outcome_from_str


@dataclass(frozen=True)
class GoldenCase:
    """One baseline entry: the :class:`Case` to run plus the outcome it should reach.

    ``case_id`` is the stable identifier the report keys on (mirrored into
    ``case.metadata["golden_id"]`` so it survives a round-trip through the pipeline).
    ``expected`` is the baseline :class:`Outcome` this case is expected to produce.
    """

    case_id: str
    case: Case
    expected: Outcome


def _to_case(entry: dict[str, object], case_id: str) -> Case:
    raw_criteria = entry.get("criteria", [])
    criteria = [str(c) for c in raw_criteria] if isinstance(raw_criteria, list) else []
    raw_output = entry.get("output")
    return Case(
        input=str(entry.get("input", "")),
        expectation=str(entry.get("expectation", "")),
        output=str(raw_output) if raw_output is not None else None,
        criteria=criteria,
        metadata={"golden_id": case_id},
    )


def _expected_outcome(entry: dict[str, object], index: int) -> Outcome:
    expected = entry.get("expected")
    if not isinstance(expected, dict) or "outcome" not in expected:
        raise ValueError(f"golden entry {index}: missing required 'expected.outcome'")
    value = str(expected["outcome"]).strip().lower()
    valid = {o.value for o in Outcome}
    if value not in valid:
        raise ValueError(
            f"golden entry {index}: unknown outcome {value!r} (expected one of {sorted(valid)})"
        )
    return outcome_from_str(value)


def load_golden(path: str | Path) -> list[GoldenCase]:
    """Load a golden-set JSON file into a list of :class:`GoldenCase`.

    The file may be either a top-level JSON array of entries or an object with a ``"cases"``
    array (so a baseline can grow a header later without breaking the loader). An entry
    without an ``id`` is keyed positionally (``case-0``, ``case-1``, …) so the file still
    loads, but giving every entry a stable id is what makes a flip report readable.
    """

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw["cases"] if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise ValueError("golden set must be a JSON array (or an object with a 'cases' array)")
    golden: list[GoldenCase] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"golden entry {index} is not a JSON object")
        case_id = str(entry.get("id") or f"case-{index}")
        golden.append(
            GoldenCase(case_id, _to_case(entry, case_id), _expected_outcome(entry, index))
        )
    return golden


def golden_to_dicts(golden: list[GoldenCase]) -> list[dict[str, object]]:
    """Serialize golden cases back to the on-disk JSON shape (round-trips ``load_golden``)."""

    out: list[dict[str, object]] = []
    for gc in golden:
        entry: dict[str, object] = {
            "id": gc.case_id,
            "input": gc.case.input,
            "expectation": gc.case.expectation,
            "criteria": list(gc.case.criteria),
            "expected": {"outcome": gc.expected.value},
        }
        if gc.case.output is not None:
            entry["output"] = gc.case.output
        out.append(entry)
    return out


def save_golden(path: str | Path, golden: list[GoldenCase]) -> None:
    """Write ``golden`` to ``path`` as pretty-printed JSON (the format ``load_golden`` reads)."""

    payload = golden_to_dicts(golden)
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class GoldenSet:
    """A loaded golden set: the list of :class:`GoldenCase` plus its on-disk round-trip.

    A thin object wrapper over :func:`load_golden`/:func:`save_golden` for callers who prefer
    ``GoldenSet.load(path)`` to the bare functions; it is iterable and sized so it drops
    straight into :func:`~agentic_testing_framework.regression.runner.run_regression`.
    """

    cases: tuple[GoldenCase, ...]

    @classmethod
    def load(cls, path: str | Path) -> GoldenSet:
        """Load a golden-set JSON file into a :class:`GoldenSet`."""

        return cls(tuple(load_golden(path)))

    def save(self, path: str | Path) -> None:
        """Write this set to ``path`` as JSON (round-trips :meth:`load`)."""

        save_golden(path, list(self.cases))

    def __iter__(self) -> Iterator[GoldenCase]:
        return iter(self.cases)

    def __len__(self) -> int:
        return len(self.cases)
