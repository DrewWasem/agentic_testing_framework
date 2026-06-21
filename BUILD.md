# How this was built

This repository is itself a piece of agentic engineering. The framework was
designed, implemented, audited, and hardened by **directing AI coding agents** —
with a human (Drew Wasem) as the orchestrator who set the direction, fixed the
invariants, and held the acceptance bar — rather than hand-writing the modules.
The harness is the product; this page is the record of *how it got built*, since
the build process is itself part of what the repo is meant to demonstrate.

## The process

- **Plan first, then build under fixed invariants.** A small set of load-bearing
  invariants — deterministic checks ground the LLMs (never run beside them), one
  shared append-only evidence ledger, the orchestrator adjudicates and never
  averages, cost-by-construction model tiering, an offline-first mock path, and a
  standard-library-only core — were settled up front and treated as
  non-negotiable. Every change was checked back against them.

- **A skeptical reviewer on every phase.** Each major phase was reviewed by a
  *separate* adversarial agent whose job was to find problems, not to approve —
  because a generator critiquing its own work is far weaker than an evaluator
  tuned to be skeptical. That loop caught a genuine, ledger-corrupting bug:
  `bool("false")` is `True` in Python, so a judge model that emitted the JSON
  *string* `"false"` was being recorded as a **passing** result. It was fixed
  with an explicit truthiness coercion in the judging layer — and a regression
  test now pins the behavior.

- **A read-only review of a wider set of agentic projects.** The framework was
  sharpened by surveying other agentic systems for reusable patterns — strictly
  read-only, with nothing copied in. Only generalizable ideas (golden-set
  regression, prompt-as-code versioning, "judge the judge" meta-evaluation)
  informed the roadmap; no external project's content lives in this repo.

- **A documentation audit, then over-testing.** An automated documentation-audit
  pass was run against the framework; its findings were fixed and the offline
  test count grew from 63 to 83 — including tests that assert the project's own
  design promises (the zero-dependency import, the never-average invariant).

- **A visible trail.** Everything shipped as a clean, reviewable sequence of pull
  requests — build → ecosystem-review → audit-fix → this showcase pass — rather
  than opaque direct-to-`main` commits, so the engineering is auditable from the
  Git history alone.

## Why it matters

Auditability is the framework's whole thesis, and the build practiced what the
harness preaches: establish the hard facts first, let independent reviewers
disagree, and make every decision traceable to the evidence behind it. The same
discipline the tribunal applies to an agent under test was applied to building
the tribunal itself.

---

*Built with [Claude Code](https://claude.com/claude-code), directed by the author.*
