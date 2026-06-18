"""The ``atf`` command-line entry point.

``atf run --example`` runs the README example end to end, fully offline, with no API key.
``atf version`` prints the version.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__
from .core.case import Case
from .core.types import Verdict
from .tribunal.pipeline import build_pipeline


def _example_case() -> Case:
    return Case(
        input="Write a SQL query for total revenue per region in 2025.",
        output=(
            "SELECT region, SUM(amount) AS revenue FROM orders WHERE year=2025 GROUP BY region;"
        ),
        expectation="A correct, runnable SQL query answering the question.",
        criteria=[
            "Groups by region",
            "Sums a revenue/amount column",
            "Filters to the year 2025",
            "Is syntactically valid SQL",
        ],
    )


def _print_verdict(verdict: Verdict) -> None:
    print(f"VERDICT: {verdict.outcome.value.upper()}")
    print(f"Rationale: {verdict.rationale}")
    if verdict.cited_findings:
        print(f"Cited findings: {', '.join(verdict.cited_findings)}")
    print(f"Model calls: {verdict.total_llm_calls} (gated={verdict.gated})")
    print("Evidence ledger:")
    for finding in verdict.findings:
        status = "" if finding.passed is None else (" PASS" if finding.passed else " FAIL")
        head = f"  [{finding.id}] {finding.source} ({finding.severity.value}{status})"
        print(f"{head}: {finding.message}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atf", description="Agentic Testing Framework")
    sub = parser.add_subparsers(dest="command")
    run_parser = sub.add_parser("run", help="Run the tribunal on a case")
    run_parser.add_argument(
        "--example", action="store_true", help="Run the built-in README example offline"
    )
    sub.add_parser("version", help="Print the version")

    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "run":
        if args.example:
            pipeline = build_pipeline()  # offline MockProvider — no API key needed
            _print_verdict(pipeline.run_case(_example_case()))
            return 0
        run_parser.error("nothing to run; try: atf run --example")
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
