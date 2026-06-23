# Meta-evaluation results

**Honest headline: on these labeled sets the ATF tribunal is *as accurate* as a single-judge baseline — it does not beat it on raw accuracy. Its measured value is (1) auditability — every verdict ships with a cited evidence ledger a single judge doesn't produce — and (2) the meta-evaluation itself, which found and then fixed a real calibration flaw in ATF: an over-strict adversarial lens that had been failing correct edge-case outputs.**

*Run dates: 2026-06-22/23. Judge backend: `ClaudeCLIProvider` (the authenticated `claude` CLI). Exploratory results, reported as-is.*

## Method

- **ATF** = the full tribunal (clerk → grounded reviewer → 4-lens council → adjudicating orchestrator).
- **Baseline** = a single "is this output good? PASS/FAIL + reason" model call — the naive LLM-as-judge.
- **Same model for both**, so the experiment isolates the *architecture* (a structured tribunal vs. one call), not model power.
- A verdict counts as `pass` iff `outcome == PASS` (`FAIL` or `INCONCLUSIVE` → `fail`). Gold labels are human-obvious; each case's `criteria` state the requirement **without revealing whether this output meets it**, so the judge has to actually evaluate.
- κ = Cohen's kappa vs the gold labels.

## Result 1 — easy / moderate cases: parity at both tiers

An 8-case stratified subset of `labeled.json` (2 clearly-good, 1 clearly-bad, 3 subtle-bad, 2 subtle-good):

| judge model | ATF | single-judge baseline |
|---|:---:|:---:|
| Opus 4.8  | 8/8 (κ=1.0) | 8/8 (κ=1.0) |
| Haiku 4.5 | 8/8 (κ=1.0) | 8/8 (κ=1.0) |

A single judge — even Haiku — is already at ceiling here. The "subtle" cases (a SQL query filtered to 2024 not 2025; a summary that adds an unsourced "unanimously"; Apollo-11-in-1968) are subtle to a *skimming human*, not to a focused LLM. They can't separate the tribunal from a single call.

## Result 2 — hard cases: the meta-eval finds, then fixes, a real flaw

`hard-cases.json` is 8 cases written so a single judge must *verify*, not skim — 5 with a confident-but-wrong output (a fabricated cause buried among two real ones; an even-length `median` bug; a `% 4`-only leap-year bug; a hollow "summary" that states no finding; a wrong-speed calculation) and 3 correct-but-unusual (`0.999… = 1`; `~i` mirror-indexing in a palindrome check; `list(dict.fromkeys(items))` dedup). Judge: Haiku 4.5.

**Before the fix — `council` v1 / `orchestrator` v1:**

| | ATF | baseline |
|---|:---:|:---:|
| hard cases (Haiku) | **6/8 (κ=0.39)** | 8/8 (κ=1.0) |

ATF *lost*. It correctly failed all 5 buried-error cases, but **wrongly failed two correct ones**: the `~i` palindrome (its adversarial lens demanded *case-insensitivity* the task never asked for) and the `dict.fromkeys` dedup (it objected the code would *crash on unhashable items* — also out of scope). The orchestrator let those out-of-scope objections flip a PASS into a FAIL — violating ATF's own stated rule, *"grade only against the stated expectation."*

**The fix — `council` v2 / `orchestrator` v2** (a prompt-as-code change, version-bumped): anchor the adversarial lens *and* the orchestrator to the stated expectation — an out-of-scope concern is recorded as a finding but **must not** flip a PASS to a FAIL.

**After the fix:**

| | ATF | baseline |
|---|:---:|:---:|
| hard cases (Haiku) | **8/8 (κ=1.0)** | 8/8 (κ=1.0) |

Both false-fails flipped to PASS; **all 5 buried-error cases still FAIL** (no over-correction). ATF now matches the single judge — and adds the cited ledger (see [`../live-run/report.html`](../live-run/report.html), a real run that correctly fails the even-length median bug with 18 findings).

## What this does and doesn't prove

- **Does:** the real (non-mock) path works end to end on live models; after the v2 fix ATF is well-calibrated and **at parity** with a single judge on both easy and hard cases; and the meta-eval can find a real flaw and *verify the fix* — the build → measure → improve loop an evaluation tool exists to enable.
- **Doesn't:** that ATF is *more accurate* than a single frontier judge. On these sets it isn't — it's equal. Its edge is **auditability and calibration**, not a raw-accuracy win. Anyone claiming "better verdicts" should show data; this is the data.
- **Caveats:** small sets (8 cases each); same-model design; binary PASS-vs-not mapping; the hard set was run at the Haiku tier; one run per case (no multi-trial variance). Treat as exploratory.

## Reproduce

```bash
# offline plumbing (no API key, deterministic mock — numbers are not meaningful):
atf metaeval --dataset examples/metaeval/hard-cases.json

# real judge (spends Claude usage; same model judges ATF and the baseline):
atf metaeval --dataset examples/metaeval/hard-cases.json --judge claude-cli --model claude-haiku-4-5
```

## Artifacts

- [`hard-cases.json`](hard-cases.json) — the 8 hard cases (5 fail-gold, 3 pass-gold).
- [`../live-run/report.html`](../live-run/report.html) — a real Haiku tribunal run on the even-length median bug: FAIL, 18 cited findings — the auditable ledger a single judge doesn't give you.
