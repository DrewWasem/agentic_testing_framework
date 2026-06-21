# Agentic Testing Framework

**An adversarial test harness for AI agents, with an auditable evaluation tribunal.**

[![CI](https://github.com/DrewWasem/agentic_testing_framework/actions/workflows/ci.yml/badge.svg)](https://github.com/DrewWasem/agentic_testing_framework/actions/workflows/ci.yml)
[![Python 3.10–3.13](https://img.shields.io/badge/python-3.10--3.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![tests: 83 offline & free](https://img.shields.io/badge/tests-83%20offline%20%26%20free-brightgreen.svg)](#status)
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

Most eval tools either string-match (brittle) or ask a single LLM "is this good?"
(lenient and unauditable). The tribunal makes different design choices — and two
of them appear to be unclaimed across the tools surveyed:

| | promptfoo | DeepEval | Ragas | Inspect AI | **ATF** |
|---|:---:|:---:|:---:|:---:|:---:|
| Deterministic checks **ground** the judge (injected as fact) | – | – | – | – | **✓** |
| Single shared **citable evidence ledger** → written rationale | per-assert | – | traces | – | **✓** |
| Orchestrator **adjudicates, never averages** | – | – | vote | majority | **✓** |
| Distinct-lens **panel** (not a self-ensemble) | – | – | – | – | **✓** |
| Hard gate **short-circuits before any tokens are spent** | partial | partial | – | – | **✓** |
| Offline + **standard-library-only, zero-dependency core** | – | – | – | – | **✓** |

This is a capability sketch, not a benchmark — each of those tools does plenty
that this one doesn't (managed datasets, large metric libraries, dashboards). The
point is the *shape* of the evaluation, not a feature count.

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

Run the whole suite the same way — `pytest` (83 tests, all offline, no API key).
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
