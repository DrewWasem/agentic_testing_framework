"""The ``atf`` command-line entry point.

``atf run --example`` runs the README example end to end, fully offline, with no API key.
``--html``/``--junit`` write reports; ``--gate`` returns exit 1 on a non-PASS so CI blocks.
``--cache DIR`` reuses model responses from disk; ``--show-cost`` prints a per-stage rollup
of calls, latency, and estimated dollars (at default-tier list prices) — the cost-by-
construction proof: the clerk is free, a hard gate spends $0, and a cache hit is $0.
``atf version`` prints the version.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .core.case import Case
from .core.types import Outcome, Verdict
from .metrics import MetricReport, run_metrics
from .providers.mock import MockProvider
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


def _print_cost_rollup(verdict: Verdict) -> None:
    """Print a per-stage cost rollup: stage, calls, latency, estimated dollars.

    Wording stays honest — the dollar figure is an estimate at default-tier list prices, not
    a bill. A gated case shows the short-circuit line: 0 model calls, $0.
    """

    print("Cost rollup (estimated at default-tier list prices):")
    for cost in verdict.stage_costs:
        print(
            f"  {cost.stage:<13} calls={cost.llm_calls:<2} "
            f"latency={cost.latency_s * 1000:7.2f}ms  est-cost=${cost.cost_usd:.6f}"
        )
    print(
        f"  {'TOTAL':<13} calls={verdict.total_llm_calls:<2} "
        f"latency={verdict.total_latency_s * 1000:7.2f}ms  est-cost=${verdict.total_cost_usd:.6f}"
    )
    if verdict.gated:
        print("  hard gate short-circuited: 0 model calls, $0 spent")


def _print_metric_report(report: MetricReport) -> None:
    """Print each metric's normalized score and the aggregate mean/pass-fail.

    The metrics are an opt-in lens library: this only runs when ``--metrics`` is passed, so
    the default ``atf run --example`` keeps its exact six-call cost.
    """

    print("Metrics (LLM-judge lenses, normalized 0..1):")
    for finding in report.findings:
        name = str(finding.metadata.get("metric", finding.source))
        score = finding.metadata.get("score")
        status = "PASS" if finding.passed else "FAIL"
        shown = f"{score:.3f}" if isinstance(score, int | float) else "n/a"
        print(f"  {name:<16} {shown}  [{status}]  {finding.message}")
    verdict = "PASS" if report.passed else "FAIL"
    print(
        f"  {'AGGREGATE':<16} mean={report.mean:.3f} "
        f"(threshold {report.threshold:.2f}) -> {verdict}"
    )


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
    run_parser.add_argument(
        "--cache",
        metavar="DIR",
        help="Reuse model responses from a content-addressed on-disk cache in DIR",
    )
    run_parser.add_argument(
        "--show-cost",
        action="store_true",
        help="Print a per-stage rollup of calls, latency, and estimated cost",
    )
    run_parser.add_argument(
        "--metrics",
        metavar="NAMES",
        help="Comma-separated LLM-judge metrics to also run (e.g. g_eval,faithfulness,toxicity)",
    )
    sub.add_parser("version", help="Print the version")

    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "run":
        if args.example:
            case = _example_case()
            # offline MockProvider — no API key needed; --cache reuses responses from disk
            pipeline = build_pipeline(cache_dir=args.cache)
            verdict = pipeline.run_case(case)
            _print_verdict(verdict)
            if args.show_cost:
                _print_cost_rollup(verdict)
            if args.metrics:
                names = [n.strip() for n in args.metrics.split(",") if n.strip()]
                # A separate offline provider — metrics are opt-in and standalone, so the
                # tribunal's six model calls above are unaffected by running them.
                report = run_metrics(case, MockProvider(), metrics=names)
                _print_metric_report(report)
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
