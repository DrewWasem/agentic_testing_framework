"""The ``atf`` command-line entry point.

``atf run --example`` runs the README example end to end, fully offline, with no API key.
``atf run --input … --output … --expectation …`` (or ``--case-file case.json``) grades a case
of your own through the same tribunal. ``--html``/``--junit`` write reports; ``--open`` opens
the HTML in a browser; ``--gate`` returns exit 1 on a non-PASS so CI blocks. ``--cache DIR``
reuses model responses from disk; ``--show-cost`` prints a per-stage rollup of calls, latency,
and estimated dollars (at default-tier list prices) — the cost-by-construction proof: the
clerk is free, a hard gate spends $0, and a cache hit is $0. ``atf version`` prints the version.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from collections.abc import Sequence

from . import __version__
from .core.case import Case
from .core.finding import Finding
from .core.types import Outcome, Verdict
from .metaeval import MetaEvalReport, load_labeled, render_markdown, run_metaeval
from .metrics import MetricReport, run_metrics
from .providers.base import Provider
from .providers.claude_cli import ClaudeCLIProvider
from .providers.mock import MockProvider
from .regression import RegressionReport, load_golden, run_regression, update_baseline
from .reporting import render_html, render_junit, render_suite_html
from .tribunal.pipeline import build_pipeline

# ANSI colour codes used by the human-readable stdout. Kept as a tiny table so the colour
# helper stays a one-liner and the styling intent is named, not scattered as magic numbers.
_GREEN = "32"
_RED = "31"
_YELLOW = "33"
_DIM = "2"
_BOLD = "1"

# Map an outcome to the colour its banner/badge/summary line is painted in when colour is on.
_OUTCOME_COLOR = {
    Outcome.PASS: _GREEN,
    Outcome.FAIL: _RED,
    Outcome.INCONCLUSIVE: _YELLOW,
}


def _c(text: str, code: str, *, on: bool) -> str:
    """Wrap ``text`` in an ANSI colour escape when ``on``; otherwise return it unchanged.

    The single choke point for colour: every coloured span goes through here, so the plain
    path (a non-tty, ``NO_COLOR``, or ``--no-color``) is guaranteed escape-free and the tests
    that parse stdout see exactly the bare text.
    """

    return f"\033[{code}m{text}\033[0m" if on else text


def _color_enabled(no_color: bool) -> bool:
    """Colour is opt-out and TTY-aware: on only at an interactive terminal, unless suppressed.

    Disabled when stdout is not a tty (so piped/captured output — including pytest — stays
    plain), when ``NO_COLOR`` is set (the cross-tool convention), or when ``--no-color`` was
    passed. All three must clear for colour to turn on.
    """

    if no_color or os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


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


def _print_verdict(verdict: Verdict, *, no_color: bool = False) -> None:
    """Print a scannable, colour-aware verdict: banner, one-line summary, then the evidence.

    The layout is built to be read top-down: a coloured ``── VERDICT: PASS ──`` banner, a
    single summary line of the counts that matter, the rationale, the cited findings, the full
    evidence ledger (grouped by source, ids dimmed, a finding's PASS/FAIL coloured), and last
    the advisory section for beyond-spec notes. Colour is opt-out and TTY-aware via ``_c``;
    when it is off the output is plain text — ``VERDICT: PASS`` and the summary line are always
    present as bare substrings so the stdout stays parseable.
    """

    on = _color_enabled(no_color)
    outcome = verdict.outcome
    label = outcome.value.upper()
    code = _OUTCOME_COLOR.get(outcome, _YELLOW)
    banner = _c(f"── VERDICT: {label} ──", f"{_BOLD};{code}", on=on)
    print(banner)
    # Advisory findings are beyond-spec notes that never drove the verdict, so they are split
    # out of the verdict-driving ledger and counted separately in the summary line below.
    advisory = [f for f in verdict.findings if f.advisory]
    ledger = [f for f in verdict.findings if not f.advisory]
    summary = (
        f"{len(ledger)} findings · {len(advisory)} advisory · "
        f"{verdict.total_llm_calls} model calls (gated={verdict.gated})"
    )
    print(_c(summary, _DIM, on=on))
    print()
    print(f"Rationale: {verdict.rationale}")
    if verdict.cited_findings:
        print(f"Cited findings: {', '.join(verdict.cited_findings)}")
    print("Evidence ledger:")
    for finding in ledger:
        print(f"  {_format_ledger_line(finding, on=on)}")
    if advisory:
        print(_c("Also noted — advisory (beyond the stated spec):", _DIM, on=on))
        for finding in advisory:
            fid = _c(f"[{finding.id}]", _DIM, on=on)
            head = f"  {fid} {finding.source} ({finding.severity.value})"
            print(f"{head}: {finding.message}")


def _format_ledger_line(finding: Finding, *, on: bool) -> str:
    """Format one ledger finding: a dimmed id, the source/severity, a coloured PASS/FAIL.

    A failed finding's status is painted red and a passed one green when colour is on; an
    informational finding (``passed is None``) carries no status token at all.
    """

    fid = _c(f"[{finding.id}]", _DIM, on=on)
    if finding.passed is None:
        status = ""
    elif finding.passed:
        status = " " + _c("PASS", _GREEN, on=on)
    else:
        status = " " + _c("FAIL", _RED, on=on)
    head = f"{fid} {finding.source} ({finding.severity.value}{status})"
    return f"{head}: {finding.message}"


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


def _print_suite_summary(results: Sequence[tuple[str, Verdict]], *, no_color: bool = False) -> None:
    """Print a per-case suite summary: a header count line, then one coloured line per case.

    Each case line leads with its outcome (PASS green / FAIL red / INCONCLUSIVE yellow when
    colour is on) so a long suite scans at a glance; the count of non-PASS cases is the number
    ``--gate`` keys off. Colour is opt-out and TTY-aware via ``_c``; the plain path prints the
    bare outcome word so the summary stays parseable.
    """

    on = _color_enabled(no_color)
    n_pass = sum(1 for _, v in results if v.outcome is Outcome.PASS)
    n_fail = sum(1 for _, v in results if v.outcome is Outcome.FAIL)
    n_inconclusive = sum(1 for _, v in results if v.outcome is Outcome.INCONCLUSIVE)
    header = (
        f"Suite: {len(results)} case(s) · {n_pass} pass · "
        f"{n_fail} fail · {n_inconclusive} inconclusive"
    )
    print(_c(header, _BOLD, on=on))
    width = max((len(name) for name, _ in results), default=0)
    for name, verdict in results:
        code = _OUTCOME_COLOR.get(verdict.outcome, _YELLOW)
        mark = _c(f"{verdict.outcome.value.upper():<12}", code, on=on)
        print(f"  {mark} {name:<{width}}  {verdict.rationale}")


def _run_eval_command(args: argparse.Namespace) -> int:
    """Run a whole suite of cases through the tribunal and report it as a browsable artifact.

    Loads the JSON array from ``--cases`` (a bad/non-array file exits 2, cleanly), builds the
    pipeline once on the chosen judge backend, runs every case, and prints a per-case summary.
    With ``--html`` it writes :func:`render_suite_html` (and ``--open`` opens it); with
    ``--gate`` it exits 1 if ANY case's outcome is not PASS, else 0 — the suite-wide analogue
    of :func:`_exit_code`.
    """

    if args.open and not args.html:
        args._eval_parser.error("--open needs an HTML report to open; pass --html PATH too")
    loaded = _load_cases_file(args.cases)
    if loaded is None:
        return 2
    judge = _build_judge_provider(args.judge, args.model)
    pipeline = build_pipeline(judge)
    results = [(name, pipeline.run_case(case)) for name, case in loaded]
    _print_suite_summary(results, no_color=args.no_color)
    ok = True
    if args.html:
        ok = _write_report(args.html, render_suite_html(results), "suite HTML") and ok
        if ok and args.open:
            _open_report(args.html)
    if not ok:
        return 1
    if args.gate and any(v.outcome is not Outcome.PASS for _, v in results):
        return 1
    return 0


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


# Indirection so a test can monkeypatch the browser launch (``cli._open``) and assert the
# path it was handed without actually opening a window — keeps ``--open`` CI-safe.
_open = webbrowser.open


def _open_report(path: str) -> None:
    """Open a written report in the default browser (guarded so tests don't launch one)."""

    _open(f"file://{path}")
    print(f"Opened {path} in the default browser")


def _case_from_dict(data: object, path: str) -> Case | None:
    """Build a :class:`Case` from one decoded JSON object, validating field TYPES.

    Shared by the single-case ``--case-file`` loader and the suite ``--cases`` loader so both
    enforce the same contract: the payload must be an object with string ``input`` and
    ``expectation``; ``output`` is a string or omitted; ``criteria`` is a list of strings or
    omitted. On any violation it reports cleanly to stderr and returns ``None`` — a non-string
    value must never reach a downstream check and crash with a traceback (e.g. the clerk's
    ``(output or "").split()``).
    """

    if not isinstance(data, dict):
        print(f"error: case file {path} must be a JSON object", file=sys.stderr)
        return None
    input_ = data.get("input")
    expectation = data.get("expectation")
    output = data.get("output")
    criteria = data.get("criteria")
    if not isinstance(input_, str) or not isinstance(expectation, str):
        print(
            f"error: case file {path} needs string 'input' and 'expectation'",
            file=sys.stderr,
        )
        return None
    if output is not None and not isinstance(output, str):
        print(f"error: case file {path}: 'output' must be a string or omitted", file=sys.stderr)
        return None
    if criteria is not None and not (
        isinstance(criteria, list) and all(isinstance(c, str) for c in criteria)
    ):
        print(f"error: case file {path}: 'criteria' must be a list of strings", file=sys.stderr)
        return None
    return Case(
        input=input_,
        expectation=expectation,
        output=output,
        criteria=tuple(criteria or ()),
    )


def _read_json_file(path: str, kind: str) -> object | None:
    """Read and JSON-decode ``path``; report a missing/unreadable/malformed file cleanly.

    Returns the decoded payload, or ``None`` after printing an ``error:`` line to stderr — so a
    bad ``--case-file``/``--cases`` path exits non-zero without a traceback.
    """

    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        print(f"error: could not read {kind} file {path}: {exc}", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"error: {kind} file {path} is not valid JSON: {exc}", file=sys.stderr)
        return None


def _load_case_file(path: str) -> Case | None:
    """Load a single case from a JSON file: ``{input, output?, expectation, criteria?}``.

    Returns ``None`` and reports cleanly to stderr on a missing/unreadable/malformed file or a
    payload that fails type validation, so a bad ``--case-file`` exits non-zero without a
    traceback — the same contract as :func:`_write_report`.
    """

    data = _read_json_file(path, "case")
    if data is None:
        return None
    return _case_from_dict(data, path)


def _load_cases_file(path: str) -> list[tuple[str, Case]] | None:
    """Load a JSON ARRAY of cases for ``atf eval``, as ``(name, case)`` pairs in file order.

    The file must be a JSON array; each element is a case object validated by
    :func:`_case_from_dict`. A case's name is its ``id`` or ``name`` field if a non-empty
    string, else ``case-{i}`` by position. A missing/malformed/non-array file or any element
    that fails validation reports cleanly to stderr and returns ``None`` (exit 2, no traceback).
    """

    data = _read_json_file(path, "cases")
    if data is None:
        return None
    if not isinstance(data, list):
        print(f"error: cases file {path} must be a JSON array of case objects", file=sys.stderr)
        return None
    if not data:
        print(f"error: cases file {path} contains no cases", file=sys.stderr)
        return None
    cases: list[tuple[str, Case]] = []
    for i, item in enumerate(data):
        case = _case_from_dict(item, path)
        if case is None:
            return None
        name = item.get("id") or item.get("name")
        label = name if isinstance(name, str) and name else f"case-{i}"
        cases.append((label, case))
    return cases


def _case_from_args(args: argparse.Namespace) -> Case | None:
    """Build the case the ``run`` command will judge, or ``None`` if there is nothing to run.

    Resolution order: ``--example`` (the built-in case) → ``--case-file`` (load from JSON) →
    inline ``--input``/``--output``/``--expectation`` flags. The inline form requires at least
    ``--expectation`` and ``--output`` (an empty ``--output`` is still a runnable, judgeable
    result); a partial inline case fails through ``argparse`` rather than silently doing nothing.
    """

    if args.example:
        return _example_case()
    if args.case_file:
        return _load_case_file(args.case_file)
    if args.expectation is not None or args.output is not None or args.input is not None:
        if args.expectation is None or args.output is None:
            args._run_parser.error(
                "an inline case needs at least --output and --expectation "
                "(or use --case-file / --example)"
            )
        return Case(
            input=args.input or "",
            expectation=args.expectation,
            output=args.output,
            criteria=tuple(args.criteria or ()),
        )
    return None


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
    run_parser.add_argument(
        "--input", metavar="TEXT", help="The task given to the agent (for an inline case)"
    )
    run_parser.add_argument(
        "--output", metavar="TEXT", help="The agent's result to judge (for an inline case)"
    )
    run_parser.add_argument(
        "--expectation",
        metavar="TEXT",
        help="Plain-English description of a good result (for an inline case)",
    )
    run_parser.add_argument(
        "--criteria",
        metavar="TEXT",
        action="append",
        help="A criterion to grade one by one; repeat the flag for several",
    )
    run_parser.add_argument(
        "--case-file",
        metavar="PATH",
        help='Load a single case from JSON: {"input":…, "output":…, "expectation":…, '
        '"criteria":[…]} (output/criteria optional)',
    )
    run_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the HTML report in the default browser after writing it (requires --html)",
    )
    run_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable coloured terminal output (also honoured via NO_COLOR / a non-tty)",
    )
    # Stash the run subparser so _case_from_args can raise a clean argparse error for a
    # partial inline case without main having to thread the parser into the helper.
    run_parser.set_defaults(_run_parser=run_parser)
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
    eval_parser = sub.add_parser(
        "eval", help="Run a suite of cases and emit one browsable summary + HTML report"
    )
    eval_parser.add_argument(
        "--cases",
        metavar="PATH",
        required=True,
        help='JSON array of cases: [{"input":…, "expectation":…, "output"?, "criteria"?, '
        '"id"?}, …] (output/criteria/id optional)',
    )
    eval_parser.add_argument(
        "--judge",
        choices=("mock", "claude-cli"),
        default="mock",
        help="Judge backend: mock (offline default) or claude-cli (a real Claude run)",
    )
    eval_parser.add_argument(
        "--model",
        metavar="MODEL",
        help="Model id for the claude-cli judge (e.g. claude-opus-4-8); ignored for mock",
    )
    eval_parser.add_argument(
        "--html", metavar="PATH", help="Write a self-contained HTML suite report to PATH"
    )
    eval_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the HTML report in the default browser after writing it (requires --html)",
    )
    eval_parser.add_argument(
        "--gate",
        action="store_true",
        help="Exit 1 when ANY case's verdict is not PASS (so CI fails the job)",
    )
    eval_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable coloured terminal output (also honoured via NO_COLOR / a non-tty)",
    )
    # Stash the eval subparser so _run_eval_command can raise a clean argparse error for
    # --open-without---html, the same way the run command does.
    eval_parser.set_defaults(_eval_parser=eval_parser)
    sub.add_parser("version", help="Print the version")

    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "metaeval":
        return _run_metaeval_command(args.dataset, args.judge, args.model, args.out)
    if args.command == "regression":
        return _run_regression_command(args.golden, args.max_drift, args.update_baseline)
    if args.command == "eval":
        return _run_eval_command(args)
    if args.command == "run":
        case = _case_from_args(args)
        if case is None:
            # A --case-file that failed to load has already reported to stderr; that is a
            # non-zero exit, not the "nothing to run" hint.
            if args.case_file:
                return 2
            run_parser.error(
                "nothing to run; try: atf run --example, "
                "atf run --input … --output … --expectation …, or atf run --case-file case.json"
            )
        if args.open and not args.html:
            run_parser.error("--open needs an HTML report to open; pass --html PATH too")
        # Default judge is the offline mock (no API key); --judge claude-cli does a real
        # Claude run. --cache reuses responses from disk regardless of backend. The case
        # came from --example, --case-file, or inline flags — it flows the same path from here.
        judge = _build_judge_provider(args.judge, args.model)
        pipeline = build_pipeline(judge, cache_dir=args.cache)
        verdict = pipeline.run_case(case)
        _print_verdict(verdict, no_color=args.no_color)
        if args.show_cost:
            _print_cost_rollup(verdict)
        if args.metrics:
            names = [n.strip() for n in args.metrics.split(",") if n.strip()]
            # A separate offline provider — metrics are opt-in and standalone, so the
            # tribunal's six model calls above are unaffected by running them.
            report = run_metrics(case, MockProvider(), metrics=names)
            _print_metric_report(report)
        name = "example" if args.example else "case"
        ok = True
        if args.html:
            ok = _write_report(args.html, render_html(verdict, case=case), "HTML") and ok
            if ok and args.open:
                _open_report(args.html)
        if args.junit:
            ok = _write_report(args.junit, render_junit([(name, verdict)]), "JUnit") and ok
        if not ok:
            return 1
        return _exit_code(verdict, args.gate)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
