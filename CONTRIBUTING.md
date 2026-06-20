# Contributing

Thanks for looking at the Agentic Testing Framework. Issues and PRs are welcome —
especially on council lens design, adversarial categories, and additional deterministic
checks.

## Dev setup

```bash
python -m pip install -e ".[dev]"   # core has zero deps; [dev] adds pytest/ruff/mypy
pytest                              # full suite, fully offline, no API key
ruff check .                        # lint
mypy                                # type-check
```

Everything runs offline against the `MockProvider`. You do **not** need an API key to
develop or test. To run a single test:

```bash
pytest tests/test_pipeline.py::test_full_pipeline_offline_pass
```

## The invariants (please don't break these)

These are the point of the project, not incidental style:

- **Zero required dependencies in the core.** Standard library only; model SDKs are
  optional and lazily loaded. `tests/test_no_deps.py` fails if importing the package
  pulls in a third-party module.
- **Everything runs offline and free.** Every LLM stage has a mock path. A contribution
  that can't run in the offline suite won't be merged.
- **Deterministic checks ground the LLMs.** Anything plain Python can establish (counts,
  lengths, validity) is computed first and injected as fact — never asked of a model.
- **One shared evidence ledger.** Every check and reviewer emits a structured `Finding`;
  nothing flows as a bare pass/fail. The verdict cites finding ids.
- **The orchestrator adjudicates; it never averages.** No majority vote, no mean. A single
  well-evidenced finding can outweigh several weak ones.
- **Responsible use.** Adversarial generation stays at the level of well-known robustness
  categories (prompt injection, scope-creep, contradictory instructions, edge cases). No
  step-by-step exploit synthesis.

## Prompts are code

Prompts live as versioned constants in the stage modules (`REVIEWER_SYSTEM`,
`ORCHESTRATOR_SYSTEM`, …). Changing one is a reviewable change like any other.

## Conventions

- Python; standard-library-only core. Keep `ruff` and `mypy` clean and add a test for new
  behavior.
- Commit prefixes: FEAT, FIX, ENH, PERF, REFACTOR, TEST, DOC, STYLE, CHORE, WIP.
