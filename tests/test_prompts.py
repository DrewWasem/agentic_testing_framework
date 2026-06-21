"""Prompt-as-code: the registry is well-formed, and the versions reach the verdict.

Every judge/reviewer/orchestrator/generator/metric system prompt carries a stable id, a
version, and a changelog; a verdict records which versions produced it. These tests guard
the registry's shape and the stamping path — the existing prompt-dependent suites (reviewer,
council, orchestrator, metrics, pipeline) cover that the WORDING is unchanged.
"""

import pytest

from agentic_testing_framework import (
    PROMPTS,
    Case,
    MockProvider,
    Prompt,
    build_pipeline,
    get_prompt,
)


def test_registry_has_every_stage_with_well_formed_entries():
    expected_ids = {"reviewer", "council", "orchestrator", "generator", "metric"}
    assert expected_ids <= set(PROMPTS)
    for prompt_id, prompt in PROMPTS.items():
        assert isinstance(prompt, Prompt)
        assert prompt.id == prompt_id  # keyed by its own id
        assert prompt.id  # non-empty
        assert prompt.version >= 1
        assert prompt.text.strip()  # non-empty body
        assert prompt.changelog  # non-empty changelog
        assert all(line.strip() for line in prompt.changelog)


def test_get_prompt_returns_the_registered_record():
    prompt = get_prompt("orchestrator")
    assert prompt is PROMPTS["orchestrator"]
    assert prompt.version >= 1


def test_get_prompt_errors_clearly_on_unknown_id():
    with pytest.raises(KeyError) as exc:
        get_prompt("nope")
    # The message names the bad id AND lists the known ones, so the failure is actionable.
    message = str(exc.value)
    assert "nope" in message
    assert "reviewer" in message


def test_verdict_records_reviewer_council_orchestrator_versions():
    pipeline = build_pipeline(MockProvider())
    verdict = pipeline.run_case(
        Case(input="q", expectation="exp", output="hello world", criteria=["c1"])
    )
    assert verdict.prompt_versions == {
        "reviewer": PROMPTS["reviewer"].version,
        "council": PROMPTS["council"].version,
        "orchestrator": PROMPTS["orchestrator"].version,
    }


def test_gated_verdict_carries_no_prompt_versions():
    # A hard gate short-circuits before any judging stage runs, so no prompt judged the case
    # and the map is empty — the version stamp reflects what actually ran.
    from agentic_testing_framework.tribunal.checks import NonEmptyCheck, default_checks

    pipeline = build_pipeline(MockProvider(), checks=[*default_checks(), NonEmptyCheck(gate=True)])
    verdict = pipeline.run_case(Case(input="q", expectation="e", output=""))
    assert verdict.gated is True
    assert verdict.prompt_versions == {}


def test_registry_text_is_the_text_the_stages_use():
    # The registry is the single source of the prompt body — a stage must not drift from it.
    from agentic_testing_framework.tribunal.orchestrator import ORCHESTRATOR_SYSTEM
    from agentic_testing_framework.tribunal.reviewer import REVIEWER_SYSTEM

    assert REVIEWER_SYSTEM == get_prompt("reviewer").text
    assert ORCHESTRATOR_SYSTEM == get_prompt("orchestrator").text
