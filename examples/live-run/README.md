# Live run

`report.html` is a **real** tribunal run — not the offline mock. It was produced by
running the full tribunal with a live judge (Claude Haiku 4.5, via the `claude` CLI)
on a case from [`../metaeval/hard-cases.json`](../metaeval/hard-cases.json): a `median()`
function that is correct for odd-length lists but returns the wrong value for even-length
ones (`median([1,2,3,4])` gives `3`, not `2.5`).

The tribunal ruled **FAIL** with 18 cited findings across the reviewer and the four council
lenses, and a written rationale that names the exact defect. Open `report.html` in a browser
to see the full evidence ledger — the part a single "is this good?" judge doesn't give you.

`report-advisory.html` is a second real run that shows **advisory (out-of-scope) findings** in
action. The case is a *correct* palindrome check that uses the non-obvious `s[~i]` mirror index.
The tribunal ruled **PASS** — it meets the stated expectation — and *also* recorded two
**advisories** the task never required but a caller might want anyway: that the `~i` idiom is
non-obvious, and that the function would raise `TypeError` on non-string input. A single judge
gives a bare verdict; the tribunal gives the verdict **plus** these beyond-spec notes in a
separate "Also noted — advisory" section, none of which counted against the PASS.

Regenerate (spends Claude usage):

```bash
atf run --example --judge claude-cli --model claude-haiku-4-5 --html report.html
```

See [`../metaeval/RESULTS.md`](../metaeval/RESULTS.md) for the honest accuracy numbers behind it.
