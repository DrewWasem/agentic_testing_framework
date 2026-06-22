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
from .metaeval import MetaEvalReport, load_labeled, render_markdown, run_metaeval
from .metrics import MetricReport, run_metrics
from .providers.base import Provider
from .providers.claude_cli import ClaudeCLIProvider
from .providers.mock import MockProvider
from .regression import RegressionReport, load_golden, run_regression, update_baseline
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


def _print_regression_report(report: RegressionReport) -> None:
    """Print a per-case table (expected vs. actual, match/flip) and the drift summary.

    The verdict is compared on its ``Outcome`` property, not its rationale, so this table is
    the audit trail for a prompt/model change: every flipped ruling is named, and the drift
    line states whether the run stayed within the budget the gate enforces.
    """

    print("Regression vs. baseline:")
    for result in report.results:
        marker = "OK  " if result.status == "match" else "FLIP"
        print(
            f"  [{marker}] {result.case_id:<24} "
            f"expected={result.expected.value:<12} actual={result.actual.value}"
        )
    verdict = "PASS" if report.passed else "FAIL"
    print(
        f"  drift={report.drift:.3f} ({report.flips}/{report.total} flipped) "
        f"budget={report.max_drift:.3f} -> {verdict}"
    )


def _build_judge_provider(judge: str, model: str | None) -> Provider:
    """Build the judge/generator backend for a command: offline mock or the real Claude CLI.

    ``mock`` (the default everywhere) keeps a command offline and free. ``claude-cli`` returns
    a :class:`ClaudeCLIProvider` so the owner can do a real live run — this is the ONLY path
    that reaches a real model, and it is never used by a test.
    """

    if judge == "claude-cli":
        return ClaudeCLIProvider(model=model)
    return MockProvider()


def _print_metaeval_report(report: MetaEvalReport) -> None:
    """Print the ATF-vs-baseline comparison table and an honest one-line verdict.

    The table mirrors the committed Markdown report: agreement, Cohen's kappa, and fail-class
    precision/recall/F1 for each judge, then the per-case rulings, then the bottom line —
    "ATF agreed with X/N vs baseline Y/N" — stated plainly, win or lose.
    """

    atf, base = report.atf, report.baseline
    print(f"Meta-evaluation over {report.size} hand-labeled case(s):")
    header = (
        f"  {'judge':<22} {'agree':>13}  {'kappa':>7}  {'fail-P':>7}  {'fail-R':>7}  {'fail-F1':>7}"
    )
    print(header)
    for s in (atf, base):
        agree = f"{s.raw_agreement:.3f} ({s.agreements}/{s.total})"
        print(
            f"  {s.label:<22} {agree:>13}  {s.cohens_kappa:>7.3f}  "
            f"{s.fail_precision:>7.3f}  {s.fail_recall:>7.3f}  {s.fail_f1:>7.3f}"
        )
    print("  per-case:")
    for row in report.rows:
        atf_mark = "ok  " if row.atf_correct else "MISS"
        base_mark = "ok  " if row.baseline_correct else "MISS"
        print(
            f"    {row.case_id:<28} gold={row.gold.value:<4} "
            f"atf={row.atf.value:<4}[{atf_mark}] base={row.baseline.value:<4}[{base_mark}]"
        )
    print(
        f"  VERDICT: ATF agreed with {atf.agreements}/{atf.total} "
        f"vs baseline {base.agreements}/{base.total} "
        f"(kappa {atf.cohens_kappa:.3f} vs {base.cohens_kappa:.3f})"
    )


def _run_metaeval_command(dataset_path: str, judge: str, model: str | None, out: str | None) -> int:
    """Score the tribunal against the single-judge baseline on a labeled dataset.

    Builds both the ATF pipeline and the baseline provider on the chosen backend (``mock`` is
    offline and the test path; ``claude-cli`` is the owner's real run), runs the meta-eval,
    prints the comparison table, and writes the Markdown report to ``--out`` if given. Exits 0;
    a bad dataset path reports cleanly and exits 2.
    """

    try:
        labeled = load_labeled(dataset_path)
    except (OSError, ValueError) as exc:
        print(f"error: could not load dataset {dataset_path}: {exc}", file=sys.stderr)
        return 2
    atf_pipeline = build_pipeline(_build_judge_provider(judge, model))
    baseline_provider = _build_judge_provider(judge, model)
    report = run_metaeval(labeled, atf_pipeline=atf_pipeline, baseline_provider=baseline_provider)
    _print_metaeval_report(report)
    if out:
        _write_report(out, render_markdown(report), "meta-eval")
    return 0


def _run_regression_command(golden_path: str, max_drift: float, update: bool) -> int:
    """Run (or rewrite) a golden set and return a CI exit code.

    With ``update`` set, re-run and write the current outcomes as the new baseline, then exit
    0 — the ``--update-baseline`` escape hatch after an intentional change. Otherwise run the
    regression and exit non-zero when drift exceeds the budget, so CI gates on it.
    """

    try:
        golden = load_golden(golden_path)
    except (OSError, ValueError) as exc:
        print(f"error: could not load golden set {golden_path}: {exc}", file=sys.stderr)
        return 2
    # An offline pipeline — regression must run free, no API key, like the rest of the CLI.
    pipeline = build_pipeline()
    if update:
        update_baseline(golden_path, pipeline, golden)
        print(f"Updated baseline written to {golden_path} ({len(golden)} cases)")
        return 0
    report = run_regression(golden, pipeline, max_drift=max_drift)
    _print_regression_report(report)
    return 0 if report.passed else 1


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
    run_parser.add_argument(
        "--judge",
        choices=("mock", "claude-cli"),
        default="mock",
        help="Judge backend: mock (offline default) or claude-cli (a real Claude run)",
    )
    run_parser.add_argument(
        "--model",
        metavar="MODEL",
        help="Model id for the claude-cli judge (e.g. claude-opus-4-8); ignored for mock",
    )
    meta_parser = sub.add_parser(
        "metaeval", help="Score the tribunal against a single-judge baseline on labeled data"
    )
    meta_parser.add_argument(
        "--dataset", metavar="PATH", required=True, help="Path to the hand-labeled dataset JSON"
    )
    meta_parser.add_argument(
        "--judge",
        choices=("mock", "claude-cli"),
        default="mock",
        help="Judge backend for BOTH judges: mock (offline default) or claude-cli (real)",
    )
    meta_parser.add_argument(
        "--model",
        metavar="MODEL",
        help="Model id for the claude-cli judge (e.g. claude-opus-4-8); ignored for mock",
    )
    meta_parser.add_argument(
        "--out", metavar="PATH", help="Write the Markdown comparison report to PATH"
    )
    reg_parser = sub.add_parser(
        "regression", help="Re-run a golden set and report verdict drift vs. the baseline"
    )
    reg_parser.add_argument(
        "--golden", metavar="PATH", required=True, help="Path to the golden-set JSON baseline"
    )
    reg_parser.add_argument(
        "--max-drift",
        type=float,
        default=0.0,
        metavar="FLOAT",
        help="Allowed fraction of flipped verdicts before the run fails (default 0.0)",
    )
    reg_parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Re-run and rewrite the baseline with the current outcomes, then exit 0",
    )
    sub.add_parser("version", help="Print the version")

    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "metaeval":
        return _run_metaeval_command(args.dataset, args.judge, args.model, args.out)
    if args.command == "regression":
        return _run_regression_command(args.golden, args.max_drift, args.update_baseline)
    if args.command == "run":
        if args.example:
            case = _example_case()
            # Default judge is the offline mock (no API key); --judge claude-cli does a real
            # Claude run. --cache reuses responses from disk regardless of backend.
            judge = _build_judge_provider(args.judge, args.model)
            pipeline = build_pipeline(judge, cache_dir=args.cache)
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
