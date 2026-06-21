"""The ``atf`` command-line entry point.

``atf run --example`` runs the README example end to end, fully offline, with no API key.
``--html``/``--junit`` write reports; ``--gate`` returns exit 1 on a non-PASS so CI blocks.
``atf version`` prints the version.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .core.case import Case
from .core.types import Outcome, Verdict
from .reporting import render_html, render_junit
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


def _exit_code(verdict: Verdict, gate: bool) -> int:
    """Return ``1`` when gating is on and the ruling is not PASS, else ``0``.

    Factored out so the CI gate decision is unit-testable without driving the whole CLI.
    """

    if gate and verdict.outcome is not Outcome.PASS:
        return 1
    return 0


def _write_report(path: str, content: str, kind: str) -> bool:
    """Write ``content`` to ``path``; report an OS error to stderr and return ``False``.

    Keeps a bad ``--html``/``--junit`` path from crashing the CLI with a traceback.
    """

    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as exc:
        print(f"error: could not write {kind} report to {path}: {exc}", file=sys.stderr)
        return False
    print(f"Wrote {kind} report to {path}")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atf", description="Agentic Testing Framework")
    sub = parser.add_subparsers(dest="command")
    run_parser = sub.add_parser("run", help="Run the tribunal on a case")
    run_parser.add_argument(
        "--example", action="store_true", help="Run the built-in README example offline"
    )
    run_parser.add_argument(
        "--html", metavar="PATH", help="Write a self-contained HTML report to PATH"
    )
    run_parser.add_argument("--junit", metavar="PATH", help="Write a JUnit XML report to PATH")
    run_parser.add_argument(
        "--gate",
        action="store_true",
        help="Exit 1 when the verdict is not PASS (so CI fails the job)",
    )
    sub.add_parser("version", help="Print the version")

    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "run":
        if args.example:
            case = _example_case()
            pipeline = build_pipeline()  # offline MockProvider — no API key needed
            verdict = pipeline.run_case(case)
            _print_verdict(verdict)
            ok = True
            if args.html:
                ok = _write_report(args.html, render_html(verdict, case=case), "HTML") and ok
            if args.junit:
                ok = _write_report(args.junit, render_junit([("example", verdict)]), "JUnit") and ok
            if not ok:
                return 1
            return _exit_code(verdict, args.gate)
        run_parser.error("nothing to run; try: atf run --example")
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
