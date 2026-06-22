# Agentic Testing Framework

**An adversarial test harness for AI agents, with an auditable evaluation tribunal.**

[![CI](https://github.com/DrewWasem/agentic_testing_framework/actions/workflows/ci.yml/badge.svg)](https://github.com/DrewWasem/agentic_testing_framework/actions/workflows/ci.yml)
[![Python 3.10–3.13](https://img.shields.io/badge/python-3.10--3.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![tests: offline & free](https://img.shields.io/badge/tests-offline%20%26%20free-brightgreen.svg)](#status)
[![lint: ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)
[![types: mypy](https://img.shields.io/badge/types-mypy-blue.svg)](https://mypy-lang.org/)

Most ways of testing an agent check the wrong thing. They assert on plumbing —
did the API return 200, did this exact string appear — and they break the moment
the wording changes. What actually matters is harder to pin down: *given a task,
did the agent's result do what it was supposed to do, and how does it hold up
when you throw difficult inputs at it?*

The Agentic Testing Framework answers that. You describe, in plain English, what a good result
looks like. The system generates test inputs (including adversarial ones), runs
them at the agent under test, and then judges the results through a layered
**tribunal** — deterministic checks, a step-by-step reviewer, a council of
reviewers with different lenses, and an orchestrator that weighs the whole record
into a final verdict with a written, evidence-cited rationale.

It is **agent-agnostic**. Through a thin adapter it can drive any agent — a
prompt, an HTTP endpoint, a CLI, a local function — not just agents built with
this framework. If you can call it, you can probe it.

---

## Why I built it

I kept seeing two kinds of agent "tests": brittle string-matching that rots
instantly, and a single LLM asked "is this good?" — which is lenient,
inconsistent, and unauditable. Neither tells you whether an agent you didn't
build will hold up under pressure.

I wanted something that treats evaluation the way a serious review process works:
hard facts established first, multiple perspectives that are allowed to disagree,
and a final ruling that has to *show its reasoning*. That's the tribunal. And I
wanted it to generate its own stress tests, so the question shifts from "does it
pass my happy-path examples" to "where does it actually break."

---

## Scope & responsible use

This is a tool for **red-teaming agents you own or are explicitly authorized to
test** — to find weaknesses before they reach production. The adversarial
generator works at the level of well-known robustness categories (prompt
injection, scope-creep, contradictory instructions, edge cases) so you can harden
your own systems. It is not built to produce attacks against systems you don't
control, and it intentionally avoids step-by-step exploit instructions. Please
use it in that spirit.

---

## What makes it different

**Deterministic checks ground the LLMs — they don't run alongside them.**
Language models are unreliable at exactly the things plain Python is perfect at:
counting words, measuring sentence length, validating that a URL is well-formed.
So those run first, and their hard facts are injected into every reviewer's
prompt. The reasoning layer never guesses at something the deterministic layer
already knows.

**One shared evidence ledger.** Every check and every reviewer writes a
structured *finding* — source, severity, message, quoted evidence — into a single
ledger. Nothing passes a bare pass/fail downstream. The final verdict can point
to exactly which findings drove it. That auditability is the whole point.

**The orchestrator adjudicates; it never averages.** Averaging a council's scores
throws away the most useful signal — *where they disagreed*. The orchestrator's
job is to find the disagreement, weigh whose evidence is stronger, and resolve
it, the way a presiding judge rules over a deliberation.

**It takes LLM-judge weakness seriously.** Reviewers are instructed to grade only
against the stated expectation, to be strict, and to quote evidence. The design
assumes judges are fallible and builds the structure to contain that, rather than
trusting a single confident verdict.

**It's cheap by construction.** Deterministic checks are free and run first.
A failed hard gate short-circuits the case before a single token is spent. The
pipeline routes by model tier — wire a small, cheap model to the reviewers and a
frontier model to the orchestrator, the one place deep reasoning earns its cost.
(The offline default runs a single mock for every stage.)

---

## How it compares

Most agent-eval tools fall into two camps: assertion/string-matching harnesses
(brittle — they break when wording changes) and "LLM-as-judge" tools that ask a
single model "is this good?" (flexible, but lenient and hard to audit). The
tribunal is a deliberate set of design choices that sit differently from both.
Rather than a competitive scorecard — which invites an argument over any single
cell — here are the choices, with where they seem common or uncommon as best I can
tell from the tools I've looked at (promptfoo, DeepEval, Ragas, Inspect AI) and the
LLM-as-judge literature, as of mid-2026. **If your tool does one of these and I've
mischaracterized it, please open an issue — I'd rather be corrected than overclaim.**

- **Deterministic checks *ground* the judge.** What plain code can establish —
  counts, lengths, URL validity, pattern presence — is computed first and injected
  into the judge's prompt as fact, so the model never re-derives (or mis-derives)
  it. Several tools run deterministic assertions and model-graded checks as
  independent, side-by-side signals; feeding the deterministic findings *into* the
  judge's context as ground truth is the piece I haven't found elsewhere.
- **The orchestrator adjudicates; it doesn't average.** Multi-judge setups are
  increasingly common, but the ones I've seen reduce the panel to a number — a
  majority vote or a mean (e.g. the "panel of judges" line of work). Here the final
  stage reads the whole disagreement and rules on it, because *where the reviewers
  disagreed* is the signal most worth keeping.
- **One shared, citable evidence ledger.** Every check and reviewer writes a
  structured finding, and the verdict must cite the findings that drove it. Tracing
  and observability tools show you *what happened*; the ledger is built so a verdict
  is reconstructible from *why*.
- **A panel of distinct lenses, not a self-ensemble** — reviewers with different
  briefs (accuracy, completeness, clarity, an adversarial skeptic), not one prompt
  run N times.
- **Cheap by construction** — free deterministic checks first, a hard gate that
  short-circuits before a token is spent, cheap models for the reviewers, a frontier
  model only for the orchestrator.
- **Offline and dependency-free** — a standard-library-only core that runs end to
  end against a mock with no API key.

What the established tools have that this one doesn't: managed datasets and
experiment tracking, large built-in metric libraries, hosted dashboards, and years
of real-world use. This is a young project with a specific point of view, not a
replacement for them. Whether these choices actually produce *better* verdicts —
not just a different shape — is an empirical question this section can't settle by
assertion. The repo ships a meta-evaluation harness (`atf metaeval`) that scores the
tribunal against a single-judge baseline on a labeled set; the numbers only mean
something against a *real* judge (the offline mock can't tell good from bad), so run
it yourself before believing any claim — including mine.

---

## How it fits together

```
[Generator] ── invents (input, expectation) ──┐
   spec-driven / adversarial / mutation        │
                                                ▼
                                   [Target: the agent under test]
                                                │  produces output
                                                ▼
   ┌───────────────────  TRIBUNAL  ───────────────────┐
   │ Clerk        deterministic checks  → findings     │  gate fails? stop, $0
   │ Reviewer     step-by-step          → findings     │  grounded by clerk
   │ Council      N lenses               → findings     │  grounded by clerk+reviewer
   │ Orchestrator adjudicates the evidence ledger      │
   └────────────────────────┬──────────────────────────┘
                            ▼
                  Verdict + written rationale
                            │
                            └─ (optional) feedback to the generator: target weak spots
```

The default council has four lenses — **accuracy, completeness, clarity, and an
adversarial skeptic** — and all of them are overridable.

Two small seams keep everything decoupled. A **provider** is how the system talks
to a judge or generator model (`complete(system, prompt) -> text`). A **target**
is how it drives the agent under test (`run(input) -> output`). Swapping the
judge backend or pointing the harness at a different agent is a one-file change.

---

## Reports & CI

A verdict is only as useful as it is inspectable, so the run can emit two
artifacts:

```bash
atf run --example --html report.html --junit results.xml --gate
```

`--html` writes a self-contained HTML page — the ruling and its rationale, the
findings the orchestrator cited, and the full evidence ledger grouped by source
and ordered by severity, so the whole reasoning chain is auditable in one file.
`--junit` writes JUnit XML that any CI runner already understands; a non-PASS
verdict becomes a `<failure>` carrying the rationale and cited findings. `--gate`
makes `atf` exit 1 on a non-PASS, so a regression in the agent under test fails
the job and blocks the merge. A copy-into-`.github/workflows/` recipe is in
[`examples/github-actions-eval.yml`](examples/github-actions-eval.yml).

`--show-cost` prints a per-stage rollup — calls, latency, and estimated dollars at
default-tier list prices — so cost-by-construction is visible, not asserted: the
clerk is free, the reviewer and council are priced at the cheap tier and only the
orchestrator at the frontier tier, and a hard gate short-circuits at $0. `--cache DIR`
adds a content-addressed on-disk cache of model responses, so re-running a suite over
an unchanged target replays from disk — a cache hit still counts as the call the case
needed but costs $0 and adds ~no latency, which the rollup shows directly. The dollar
figure is an estimate (tokens approximated from the actual text), not a bill.

---

## Metrics

The tribunal is the core evaluation; the metric library is a set of **named LLM-judge
lenses** you can run alongside it when you want a familiar, single-axis score. Each metric
asks a model to grade one dimension of the output and writes a structured finding into the
**same evidence ledger** as every other stage — the numeric score lives in the finding's
`metadata`, with quoted evidence and a pass/fail, so a metric result is as auditable as a
council finding rather than a bare number.

| Metric | Asks | Direction |
|---|---|:---:|
| **`g_eval`** | derive the rubric from the expectation, then form-fill a score | ↑ better |
| `faithfulness` | is every claim supported by the provided context? | ↑ better |
| `answer_relevancy` | does the output address the input that was asked? | ↑ better |
| `hallucination` | how much fabricated/unsupported content is present? | inverse |
| `toxicity` | how harmful or abusive is the output? | inverse |

**G-Eval is the flagship.** Rather than scoring against a fixed rubric, it has the model
*derive* the evaluation steps from the task's own expectation and criteria first (chain of
thought), then follow those steps to form-fill a 1–5 score. The derived steps are recorded
in the finding's `metadata["steps"]`, so the rubric it graded against is part of the record,
not hidden. The inverse metrics report the *amount* of the bad thing and are normalized so
every score reads the same direction: a clean output lands near 1.0 across the board.

```python
from agentic_testing_framework import Case, MockProvider, run_metrics

report = run_metrics(case, MockProvider(), metrics=["g_eval", "faithfulness", "toxicity"])
print(report.scores)   # {"g_eval": 1.0, "faithfulness": 1.0, "toxicity": 1.0}
print(report.mean, report.passed)
```

Or from the CLI, opt in with `--metrics`:

```bash
atf run --example --metrics g_eval,faithfulness,toxicity
```

`run_metrics` aggregates the per-metric scores into a mean and an overall pass/fail — the
one place averaging happens, deliberately here and never in the orchestrator, whose job is
to weigh disagreement, not collapse it. The metrics are **opt-in and standalone**: they do
not run in the default pipeline, so wiring them in never changes its cost. They **complement,
rather than replace**, the deterministic clerk and the tribunal — a metric is one model's
view of one axis; the tribunal is the adjudicated verdict. Everything here runs offline and
free through the mock, like the rest of the framework.

---

## Prompt versioning & regression

A prompt is the thing most likely to move a verdict, so the framework treats prompts as
code. Every judge, reviewer, council lens, orchestrator, generator, and metric system prompt
lives in a single registry with a stable `id`, an integer `version`, and a one-line-per-
change `changelog`; the stages source their text from there instead of holding a private
string. The version that judged a case is then **stamped onto the verdict** —
`verdict.prompt_versions` records `{stage: version}` — so a ruling states which prompt
versions produced it. That is the auditability thesis applied to the prompts themselves: a
change in behaviour after a prompt edit is attributable to a specific version bump, not a
mystery.

A **golden set** turns that into a gate. It is a small JSON baseline of cases, each paired
with the `Outcome` the tribunal is expected to reach:

```bash
atf regression --golden examples/golden.json --max-drift 0.0
```

The runner re-runs each case and reports the **flips** — rulings that no longer match the
baseline — as a `drift` fraction; the command exits non-zero when drift exceeds the budget,
so a prompt or model change that quietly broke a verdict fails CI instead of slipping
through. The comparison is on the verdict's `Outcome` **property, never the rationale text**:
a model legitimately rewording its reasoning must not register as drift. When a change is
intentional, `--update-baseline` re-runs and rewrites the expected outcomes as the new
contract. Like everything else, the golden set is stdlib-only JSON and runs offline through
the mock.

```python
from agentic_testing_framework import build_pipeline, load_golden, run_regression

report = run_regression(load_golden("examples/golden.json"), build_pipeline())
print(report.drift, report.passed)   # 0.0 True
```

---

## A test case, end to end

You can hand the tribunal a result that already exists:

```python
from agentic_testing_framework import Case

Case(
    input="Write a SQL query for total revenue per region in 2025.",
    output="SELECT region, SUM(amount) AS revenue FROM orders WHERE year=2025 GROUP BY region;",
    expectation="A correct, runnable SQL query answering the question.",
    criteria=[                       # optional — graded one by one
        "Groups by region",
        "Sums a revenue/amount column",
        "Filters to the year 2025",
        "Is syntactically valid SQL",
    ],
)
```

…or let the generator invent the inputs and the bar to clear, run them at your
agent, and report where it held and where it broke.

---

## Status

**v0.1.0 — the whole architecture runs today, offline and free.** The full tribunal
(deterministic clerk → grounded reviewer → multi-lens council → adjudicating
orchestrator) and the generator (spec-driven, adversarial, mutation, and the opt-in
adaptive loop) all run end to end against a mock backend with **no API key**:

```bash
git clone https://github.com/DrewWasem/agentic_testing_framework
cd agentic_testing_framework
pip install -e ".[dev]"     # the core has zero required deps; SDKs are optional extras

atf run --example           # grade the SQL example through the full tribunal, offline
```

That last command adjudicates the SQL example end to end against a mock backend —
no API key, no network — and prints a verdict whose every cited finding is
traceable in the evidence ledger:

```text
VERDICT: PASS
Rationale: Offline mock adjudication: deterministic checks passed and no finding failed.
Cited findings: clerk:word_count#0, clerk:sentence_length#1, clerk:url_validity#2
Model calls: 6 (gated=False)
Evidence ledger:
  [clerk:word_count#0] clerk:word_count (info): Output word count = 12.
  [clerk:sentence_length#1] clerk:sentence_length (info): Average sentence length = 12.0 words across 1 sentence(s).
  [clerk:url_validity#2] clerk:url_validity (info): No URLs found in output.
```

Run the whole suite the same way — `pytest`, all offline with no API key.
A tagged **PyPI** release is on the way; once it lands,
`pip install agentic-testing-framework` will be all you need.

Wire a real judge by passing an `AnthropicProvider` (the SDK is an optional extra,
lazily loaded — the core keeps its zero-dependency promise). The live-API path is
implemented but not exercised by the test suite; every test runs on the mock.

---

## Roadmap

> **v0.1.0 implements all six stages** at a first-pass, mock-first level. The list
> below remains the original build order and a map of where each piece lives.

1. **Deterministic foundation** — the evidence ledger and the first checks
   (word count, sentence length, URL validity). ✅ *Shipped.*
2. **Target adapter** — drive any agent: a Claude prompt, an endpoint, a CLI,
   a function. Single-turn first, designed to extend to multi-turn. ✅ *Shipped.*
3. **Grounded reviewer** — the reviewer consumes the ledger and walks criteria
   step by step. ✅ *Shipped.*
4. **Council** — multiple reviewers with distinct lenses; surfaces disagreement
   instead of averaging it away. ✅ *Shipped.*
5. **Orchestrator + pipeline** — adjudication into a final verdict and rationale;
   gating and model tiering wired end to end. ✅ *Shipped.*
6. **Generator** — spec-driven, then adversarial templates, then mutation; and
   last, an opt-in adaptive loop that feeds verdicts back to target the agent's
   weak spots. ✅ *Shipped.*

---

## Design principles

- **Zero required dependencies in the core.** It runs on the standard library;
  model SDKs are optional and lazily loaded. Everything is runnable and testable
  offline, for free, with a mock backend.
- **Every subsystem ships standalone.** The tribunal works without the generator;
  the generator works without the adaptive loop. Compose, don't entangle.
- **Show the reasoning.** A verdict you can't trace isn't worth much; every ruling
  cites the findings behind it.

---

## How this was built

This repository is itself a piece of agentic engineering: it was designed, built,
audited, and hardened by directing AI coding agents against a fixed set of
invariants, with a skeptical reviewer agent on every phase and a clean trail of
pull requests. The full story — including a real ledger-corruption bug the
reviewer caught (`bool("false")` is `True` in Python) — is in
**[BUILD.md](BUILD.md)**.

## Contributing

Issues and discussion are welcome — especially on the council lens design, the
generator's adversarial categories, and additional deterministic checks. If you
try it against a real agent, I'd love to hear where it surprised you.

## License

MIT
