"""The prompt registry — one versioned record per system prompt.

Each :class:`Prompt` pairs the exact system-prompt text a stage uses with a stable ``id``,
a monotonically-increasing ``version``, and a ``changelog`` (one line per version, newest
last). The tribunal stages and the metric base import their text from :data:`PROMPTS`
rather than holding a private constant, so a prompt change is a single, reviewable edit
*with a recorded version bump* — and the version is what gets stamped onto the verdict.

The ``metric`` entry holds the static wrapper of the shared metric prompt; the metric base
interpolates the per-metric name/instruction/scale around it, the same way the reviewer and
council wrap their text in a role header. The dynamic parts are not versioned text — the
metric's own ``instruction`` lives on each metric subclass — but the shared scaffold is.

When you edit a prompt: change the ``text`` AND append a new ``changelog`` line AND bump
``version``. The tests assert every entry has a non-empty id, ``version >= 1``, and a
non-empty changelog, so a silent text change with no version bump is the thing to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Prompt bodies (verbatim from the stages they were lifted out of) ----------------
#
# These are the SAME strings the stages used before the registry existed; each stage keeps
# its ``role_header(...)`` prefix and sources only this body from here, so the offline mock
# still routes on the role tag exactly as before.

_REVIEWER_TEXT = (
    "You are a strict evaluation reviewer. Grade the agent OUTPUT only against the stated "
    "EXPECTATION and CRITERIA -- nothing else. Quote exact evidence from the output for "
    "every judgment. Be strict: if a criterion is not clearly and fully met, mark it "
    "failed. Reward results, not intentions. The DETERMINISTIC FACTS block is ground truth "
    "established by code; rely on it and never recompute or contradict it. "
    "Respond with ONLY a JSON object of the form: "
    '{"findings": [{"criterion": str, "passed": bool, '
    '"severity": "info|low|medium|high|critical", "message": str, "evidence": str}], '
    '"summary": str}. '
    "If you are unsure about a criterion, say so explicitly in the message and mark "
    "passed=false. Do not guess or fabricate."
)

_ORCHESTRATOR_TEXT = (
    "You are the presiding orchestrator of an evaluation tribunal. You ADJUDICATE the "
    "evidence ledger -- you do NOT average scores or take a majority vote. Find where the "
    "reviewers disagree, weigh whose EVIDENCE is stronger, and rule. A single "
    "well-evidenced finding can outweigh several weakly-supported ones. Cite the finding "
    "ids that drive your ruling. Base your ruling ONLY on the provided findings; if the "
    'evidence is genuinely insufficient to decide, rule "inconclusive". '
    "Respond with ONLY a JSON object of the form: "
    '{"outcome": "pass|fail|inconclusive", "rationale": str, "cited_findings": [str]}.'
)

_GENERATOR_TEXT = (
    "You generate test cases for an agent under test. Invent realistic, diverse INPUTS for "
    "the described task, each paired with a clear EXPECTATION of what a good result looks "
    "like. Respond with ONLY a JSON object of the form: "
    '{"cases": [{"input": str, "expectation": str, "criteria": [str]}]}. '
    "Generate exactly N cases. If unsure, prefer simple, unambiguous cases."
)

# The council's per-lens system text is built from a template around the lens name and its
# guidance line; this is the invariant scaffold of that template. ``Council._system``
# substitutes the ``{lens}``/``{guidance}`` tokens via ``str.replace`` (NOT ``str.format``, so
# the literal JSON braces below need no escaping).
_COUNCIL_TEXT = (
    "You are one reviewer on an evaluation council, assigned a single lens: "
    "{lens}. {guidance} Judge the agent OUTPUT only against the EXPECTATION and "
    "CRITERIA, through your lens only. Treat the DETERMINISTIC FACTS as ground "
    "truth. Quote evidence. You may disagree with the other reviewers -- report "
    "what you see. Respond with ONLY a JSON object of the form: "
    '{"findings": [{"criterion": str, "passed": bool, '
    '"severity": "info|low|medium|high|critical", "message": str, '
    '"evidence": str}], "summary": str}. '
    "If unsure, say so and mark passed=false."
)

# The shared metric scaffold; ``Metric._system`` substitutes the ``{name}``/``{instruction}``/
# ``{scale}`` tokens via ``str.replace`` (NOT ``str.format``, so the literal JSON braces below
# need no escaping and ``.text`` reads as the real prompt).
_METRIC_TEXT = (
    "You are an evaluation metric named '{name}'. {instruction} "
    "Judge the agent OUTPUT only against the provided INPUT, EXPECTATION, and "
    "CRITERIA -- nothing else. Quote an exact span of evidence from the output. "
    "Score on an integer scale from 1 (worst) to {scale} (best). "
    "Respond with ONLY a JSON object of the form "
    '{"score": <number>, "reasoning": <str>, "evidence": <str>}. '
    "If you are unsure, say so in the reasoning and score conservatively. Do not "
    "guess or fabricate."
)


@dataclass(frozen=True)
class Prompt:
    """A versioned system prompt: stable id, integer version, the text, and a changelog.

    ``changelog`` is a tuple of one-line entries, newest last; its length tracks the
    version history so a reader can see why the current text reads the way it does.
    """

    id: str
    version: int
    text: str
    changelog: tuple[str, ...]


PROMPTS: dict[str, Prompt] = {
    "reviewer": Prompt(
        id="reviewer",
        version=1,
        text=_REVIEWER_TEXT,
        changelog=("v1: initial",),
    ),
    "council": Prompt(
        id="council",
        version=1,
        text=_COUNCIL_TEXT,
        changelog=("v1: initial",),
    ),
    "orchestrator": Prompt(
        id="orchestrator",
        version=1,
        text=_ORCHESTRATOR_TEXT,
        changelog=("v1: initial",),
    ),
    "generator": Prompt(
        id="generator",
        version=1,
        text=_GENERATOR_TEXT,
        changelog=("v1: initial",),
    ),
    "metric": Prompt(
        id="metric",
        version=1,
        text=_METRIC_TEXT,
        changelog=("v1: initial",),
    ),
}


def get_prompt(prompt_id: str) -> Prompt:
    """Return the registered :class:`Prompt` for ``prompt_id``, or raise a clear ``KeyError``.

    Fails loudly (listing the known ids) rather than returning ``None`` and deferring the
    error to a confusing ``AttributeError`` at the call site.
    """

    try:
        return PROMPTS[prompt_id]
    except KeyError:
        known = ", ".join(sorted(PROMPTS))
        raise KeyError(f"unknown prompt id {prompt_id!r}; known prompts: {known}") from None
