# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The Agentic Testing Framework is an adversarial test harness for AI agents with an auditable evaluation **tribunal**. You describe in plain English what a good result looks like; the system generates inputs (including adversarial ones), runs them against the agent under test, and judges the outputs through layered review that ends in a verdict with a written, evidence-cited rationale. It is **agent-agnostic** — a thin adapter lets it drive any agent: a prompt, an HTTP endpoint, a CLI, or a local function.

## Current state

**v0.1.0 is implemented — the full architecture runs offline.** The `agentic_testing_framework` package implements every layer described below; the suite is **63 tests, all offline and free**, with `ruff` and `mypy` clean.

### Commands

```bash
pip install -e ".[dev]"                                          # editable install + pytest/ruff/mypy
pytest                                                           # full offline suite (no API key, no network)
pytest tests/test_pipeline.py::test_full_pipeline_offline_pass   # a single test
ruff check .                                                     # lint
mypy                                                             # type-check (package only; configured in pyproject)
atf run --example                                                # run the README SQL example through the tribunal, offline
```

### Layout

- `core/` — `Case`, `Finding`, `EvidenceLedger`, `Verdict`, JSON parsing, model tiers, the shared `complete_json` helper
- `providers/` — the `Provider` seam; `MockProvider` (offline default), `ClaudeCLIProvider` (subprocess `claude -p`, the recommended real backend), lazy `AnthropicProvider`
- `targets/` — the `Target` seam; `function`/`http`/`cli`/`prompt` adapters + `run_target`
- `tribunal/` — `checks` (word/sentence/URL + non-empty, forbidden/required-pattern, JSON-validity, score-threshold) → `Clerk` (owns the hard gate) → `Reviewer` → `Council` → `Orchestrator` → `Pipeline`/`build_pipeline`
- `generator/` — `spec`, `adversarial`, `mutation`, `adaptive`
- `cli.py` — the `atf` entry point

The architecture and invariants below remain the contract for all new code.

## Architecture — the tribunal pipeline

```
[Generator] → [Target: agent under test] → [TRIBUNAL] → Verdict + rationale → (optional) feedback to Generator
```

The tribunal is four ordered stages that share one evidence ledger:

1. **Clerk** — deterministic checks (word count, sentence length, URL validity, …). Runs first, free. A failed **hard gate short-circuits the case before any tokens are spent**.
2. **Reviewer** — a single reviewer that walks the criteria step by step. **Grounded by the clerk's findings**: the hard facts are injected into its prompt so it never re-derives them.
3. **Council** — N reviewers with distinct lenses (default: accuracy, completeness, clarity, adversarial skeptic). Grounded by clerk + reviewer. Lenses are overridable.
4. **Orchestrator** — adjudicates the full evidence ledger into the final verdict. **It never averages** — its job is to find where reviewers disagreed, weigh whose evidence is stronger, and rule. Runs on a frontier model.

## Invariants (these are the point of the project — do not violate)

- **Deterministic checks ground the LLMs; they don't run alongside them.** Anything plain Python can establish (counting, measuring, validating) is computed first and injected as fact into every reviewer prompt. Never ask an LLM to guess what the deterministic layer already knows.
- **One shared evidence ledger.** Every check and every reviewer writes a structured *finding* — `source`, `severity`, `message`, `quoted evidence`. Nothing flows downstream as a bare pass/fail. The final verdict must be able to cite the findings that drove it. Auditability is the whole point.
- **The orchestrator adjudicates, never averages.** Averaging discards the disagreement signal, which is the most useful signal a council produces.
- **Cost by construction.** Free deterministic checks first → cheap small model for reviewers → frontier model only for the orchestrator. Route by tier; never run an expensive path once a hard gate has already failed.
- **Zero required dependencies in the core.** Standard library only. Model SDKs are optional and **lazily loaded** — importing the core must not require any SDK.
- **Everything runs offline and free.** Every stage ships a mock path so the whole pipeline is testable with no API key at zero cost. A contribution that can't run offline breaks the core promise.
- **Every subsystem ships standalone.** The tribunal works without the generator; the generator works without the adaptive loop. Compose, don't entangle.

## The two seams (keep everything else decoupled)

- **provider** — how the system talks to a judge/generator model: `complete(system, prompt) -> text`.
- **target** — how it drives the agent under test: `run(input) -> output`.

Swapping the judge backend or pointing the harness at a different agent must stay a **one-file change**. Do not leak provider- or target-specific details into the tribunal stages.

## Core type

```python
from agentic_testing_framework import Case

Case(
    input=...,         # the task given to the agent
    output=...,        # the agent's result (or let the target produce it)
    expectation=...,   # plain-English description of a good result
    criteria=[...],    # optional; graded one by one
)
```

Reviewers grade **only against the stated expectation/criteria** — strict, quoting evidence. The design assumes judges are fallible and contains that with structure, rather than trusting a single confident verdict.

## Roadmap (current build order)

1. Deterministic foundation — evidence ledger + first checks (*in progress*).
2. Target adapter — drive any agent; single-turn first, designed to extend to multi-turn.
3. Grounded reviewer — consumes the ledger, walks the criteria.
4. Council — multiple lenses; surfaces disagreement instead of averaging it away.
5. Orchestrator + pipeline — adjudication, gating, and model tiering wired end to end.
6. Generator — spec-driven → adversarial templates → mutation → opt-in adaptive loop that feeds verdicts back to target the agent's weak spots.

## Responsible use (constrains what you may build)

This is for **red-teaming agents you own or are explicitly authorized to test**. The adversarial generator operates at the level of well-known robustness categories (prompt injection, scope-creep, contradictory instructions, edge cases). It intentionally **avoids step-by-step exploit instructions** and is not for attacking systems you don't control. Keep any new adversarial features within that scope.

## Conventions

- Python; standard-library-only in the core; MIT licensed.
- Commit prefixes: FEAT, FIX, ENH, PERF, REFACTOR, TEST, DOC, STYLE, CHORE, WIP.
