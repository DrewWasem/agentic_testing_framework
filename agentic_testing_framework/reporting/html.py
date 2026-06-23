"""Render a :class:`Verdict` as a self-contained, auditable HTML report.

The whole point of the tribunal is traceability, so the report leads with the ruling and
its rationale, lists the findings the orchestrator actually cited, and then lays out the
*entire* evidence ledger grouped by source and ordered by severity — every finding shows
its id, severity, pass/fail, message, and any quoted evidence. All model- and user-supplied
text is passed through :func:`html.escape`, so a finding whose message contains markup is
shown as text, never interpreted.

Standard library only: :class:`string.Template` for the document shell, :func:`html.escape`
for every dynamic value. No templating engine, no external assets — the output is one file.
"""

from __future__ import annotations

from dataclasses import fields
from html import escape
from string import Template
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.case import Case
    from ..core.finding import Finding
    from ..core.types import StageCost, Verdict

_STYLE = """
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial,
      sans-serif;
    line-height: 1.5; margin: 0; padding: 2rem; color: #1a1a1a; background: #fafafa;
  }
  main { max-width: 56rem; margin: 0 auto; }
  h1 { font-size: 1.5rem; margin: 0 0 0.25rem; }
  h2 { font-size: 1.15rem; margin: 2rem 0 0.75rem; border-bottom: 1px solid #ddd;
       padding-bottom: 0.35rem; }
  h3 { font-size: 1rem; margin: 1.5rem 0 0.5rem; color: #333; }
  .outcome { display: inline-block; padding: 0.2rem 0.7rem; border-radius: 0.4rem;
             font-weight: 700; letter-spacing: 0.03em; }
  .outcome-pass { background: #e7f6ec; color: #186a3b; }
  .outcome-fail { background: #fdecea; color: #a01a0e; }
  .outcome-inconclusive { background: #fff4e5; color: #8a5300; }
  .meta { color: #666; font-size: 0.9rem; margin: 0.5rem 0 0; }
  .rationale { background: #fff; border: 1px solid #e2e2e2; border-left: 4px solid #888;
               border-radius: 0.4rem; padding: 0.75rem 1rem; white-space: pre-wrap; }
  ul.cited { list-style: none; padding: 0; margin: 0.5rem 0; }
  ul.cited li { display: inline-block; font-family: ui-monospace, SFMono-Regular, Menlo,
                Consolas, monospace; font-size: 0.85rem; background: #eef; color: #224;
                border-radius: 0.3rem; padding: 0.15rem 0.5rem; margin: 0.15rem 0.3rem 0.15rem 0; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; margin: 0.5rem 0; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e6e6e6; }
  th { color: #555; font-weight: 600; }
  .finding { background: #fff; border: 1px solid #e2e2e2; border-radius: 0.4rem;
             padding: 0.6rem 0.85rem; margin: 0.5rem 0; }
  .finding-head { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: baseline; }
  .fid { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
         font-size: 0.8rem; color: #555; }
  .sev { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;
         font-weight: 700; padding: 0.05rem 0.45rem; border-radius: 0.3rem; }
  .sev-info { background: #eef; color: #335; }
  .sev-low { background: #eef6ff; color: #1f5a8a; }
  .sev-medium { background: #fff4e5; color: #8a5300; }
  .sev-high { background: #fdecea; color: #a01a0e; }
  .sev-critical { background: #a01a0e; color: #fff; }
  .pf { font-size: 0.72rem; font-weight: 700; padding: 0.05rem 0.45rem; border-radius: 0.3rem; }
  .pf-pass { background: #e7f6ec; color: #186a3b; }
  .pf-fail { background: #fdecea; color: #a01a0e; }
  .finding-msg { margin: 0.35rem 0 0; }
  .evidence { margin: 0.4rem 0 0; padding: 0.4rem 0.6rem; background: #f4f4f4;
              border-radius: 0.3rem; font-family: ui-monospace, SFMono-Regular, Menlo,
              Consolas, monospace; font-size: 0.82rem; white-space: pre-wrap; }
  .evidence-label { color: #888; font-size: 0.75rem; text-transform: uppercase;
                    letter-spacing: 0.04em; }
  /* Advisory findings are beyond-spec notes that never drive the verdict, so they read
     muted and visually set apart from the verdict-driving ledger above. */
  .advisory-note { color: #777; font-size: 0.85rem; margin: 0 0 0.5rem; }
  .advisory .finding { background: #f6f6f4; border-style: dashed; border-color: #cfcfca;
                       opacity: 0.92; }
  footer { color: #999; font-size: 0.8rem; margin-top: 2.5rem; }
"""

_DOCUMENT = Template(
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>$style</style>
</head>
<body>
<main>
<header>
<h1>$title</h1>
<p><span class="outcome outcome-$outcome_class">$outcome</span></p>
<p class="meta">$meta</p>
</header>
$case_section
<h2>Rationale</h2>
<div class="rationale">$rationale</div>
<h2>Cited findings</h2>
$cited_section
$cost_section
<h2>Evidence ledger</h2>
$ledger_section
$advisory_section
<footer>Generated by the Agentic Testing Framework tribunal.</footer>
</main>
</body>
</html>
"""
)


def render_html(
    verdict: Verdict,
    *,
    case: Case | None = None,
    title: str = "Agentic Testing Framework — Verdict",
) -> str:
    """Render ``verdict`` as a single self-contained HTML document.

    Args:
        verdict: the ruling to report, carrying its evidence ledger.
        case: the case under test; if given, its input/expectation are shown for context.
        title: the document title and page header.

    Returns:
        A complete HTML document as a string. Every dynamic value is HTML-escaped.
    """

    outcome = verdict.outcome.value
    # Advisory findings are beyond-spec notes that never drive the verdict, so they are split
    # out of the verdict-driving ledger and reported in their own muted section below it.
    ledger_findings = tuple(f for f in verdict.findings if not f.advisory)
    advisory_findings = tuple(f for f in verdict.findings if f.advisory)
    meta = (
        f"Model calls: {verdict.total_llm_calls} &middot; "
        f"gated: {'yes' if verdict.gated else 'no'} &middot; "
        f"findings: {len(verdict.findings)}"
    )
    return _DOCUMENT.substitute(
        title=escape(title),
        style=_STYLE,
        outcome=escape(outcome.upper()),
        outcome_class=escape(outcome),
        meta=meta,
        case_section=_render_case(case),
        rationale=escape(verdict.rationale) or "<em>(no rationale)</em>",
        cited_section=_render_cited(verdict),
        cost_section=_render_costs(verdict.stage_costs),
        ledger_section=_render_ledger(ledger_findings),
        advisory_section=_render_advisory(advisory_findings),
    )


def _render_case(case: Case | None) -> str:
    if case is None:
        return ""
    rows = [("Input", case.input), ("Expectation", case.expectation)]
    if case.output is not None:
        rows.append(("Output", case.output))
    body = "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(str(value))}</td></tr>" for label, value in rows
    )
    criteria = ""
    if case.criteria:
        items = "\n".join(f"<li>{escape(str(c))}</li>" for c in case.criteria)
        criteria = f"<h3>Criteria</h3>\n<ul>\n{items}\n</ul>"
    return f"<h2>Case</h2>\n<table>\n{body}\n</table>\n{criteria}"


def _render_cited(verdict: Verdict) -> str:
    if not verdict.cited_findings:
        return "<p class='meta'>No findings were cited.</p>"
    items = "\n".join(f"<li>{escape(str(fid))}</li>" for fid in verdict.cited_findings)
    return f"<ul class='cited'>\n{items}\n</ul>"


def _render_costs(stage_costs: tuple[StageCost, ...]) -> str:
    if not stage_costs:
        return ""
    # Iterate the dataclass fields so this keeps working when later work appends columns
    # (e.g. latency / cost in PR B) — we render whatever fields the StageCost carries.
    field_names = [f.name for f in fields(stage_costs[0])]
    header = "".join(f"<th>{escape(name)}</th>" for name in field_names)
    rows = []
    for cost in stage_costs:
        cells = "".join(f"<td>{escape(str(getattr(cost, name)))}</td>" for name in field_names)
        rows.append(f"<tr>{cells}</tr>")
    body = "\n".join(rows)
    return f"<h2>Stage costs</h2>\n<table>\n<tr>{header}</tr>\n{body}\n</table>"


def _render_ledger(findings: tuple[Finding, ...]) -> str:
    if not findings:
        return "<p class='meta'>The ledger is empty.</p>"
    # Group by source, preserving first-seen order; within a group, highest severity first.
    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(finding.source, []).append(finding)
    sections = []
    for source, group in grouped.items():
        ordered = sorted(group, key=lambda f: f.severity.rank, reverse=True)
        cards = "\n".join(_render_finding(f) for f in ordered)
        sections.append(f"<h3>{escape(source)}</h3>\n{cards}")
    return "\n".join(sections)


def _render_advisory(findings: tuple[Finding, ...]) -> str:
    """Render advisory (beyond-spec) findings in their own muted section, or nothing.

    These are true observations the stated expectation/criteria did not require: surfaced for
    the reader but deliberately SEPARATE from the verdict-driving ledger, since the
    orchestrator must never rule on them. When there are none, emit nothing at all so a clean
    case carries no empty section.
    """

    if not findings:
        return ""
    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(finding.source, []).append(finding)
    sections = []
    for source, group in grouped.items():
        ordered = sorted(group, key=lambda f: f.severity.rank, reverse=True)
        cards = "\n".join(_render_finding(f) for f in ordered)
        sections.append(f"<h3>{escape(source)}</h3>\n{cards}")
    body = "\n".join(sections)
    return (
        "<h2>Also noted — advisory (beyond the stated spec)</h2>\n"
        "<p class='advisory-note'>True observations the stated expectation/criteria did not "
        "require. Recorded for context; they did not affect the verdict.</p>\n"
        f"<div class='advisory'>\n{body}\n</div>"
    )


def _render_finding(finding: Finding) -> str:
    sev = finding.severity.value
    parts = [
        f"<span class='fid'>{escape(finding.id)}</span>",
        f"<span class='sev sev-{escape(sev)}'>{escape(sev)}</span>",
    ]
    if finding.passed is not None:
        label = "pass" if finding.passed else "fail"
        parts.append(f"<span class='pf pf-{label}'>{label}</span>")
    if finding.criterion:
        parts.append(f"<span class='meta'>criterion: {escape(str(finding.criterion))}</span>")
    head = "".join(parts)
    evidence = ""
    if finding.evidence:
        evidence = (
            "<div class='evidence'>"
            "<span class='evidence-label'>evidence</span><br>"
            f"{escape(finding.evidence)}</div>"
        )
    return (
        "<div class='finding'>"
        f"<div class='finding-head'>{head}</div>"
        f"<p class='finding-msg'>{escape(finding.message)}</p>"
        f"{evidence}"
        "</div>"
    )
