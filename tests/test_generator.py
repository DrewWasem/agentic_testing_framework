"""Generator: spec-driven (with fallback), adversarial (category-level), mutation."""

import json

import pytest

from agentic_testing_framework import (
    ADVERSARIAL_CATEGORIES,
    AdversarialGenerator,
    Case,
    GenSpec,
    MockProvider,
    Mutator,
    SpecGenerator,
)


def test_spec_generator_parses_model_cases():
    scripted = json.dumps(
        {
            "cases": [
                {"input": "i1", "expectation": "e1", "criteria": ["a"]},
                {"input": "i2", "expectation": "e2", "criteria": []},
            ]
        }
    )
    cases = SpecGenerator(MockProvider([scripted])).generate(
        GenSpec(task="t", expectation="def", n=2)
    )
    assert len(cases) == 2
    assert cases[0].input == "i1"
    assert cases[0].metadata["source"] == "spec-generator"


def test_spec_generator_falls_back_when_empty():
    # The unconfigured mock returns {"cases": []}; the generator must not yield zero cases.
    cases = SpecGenerator(MockProvider()).generate(GenSpec(task="do a thing", expectation="d", n=3))
    assert len(cases) == 3
    assert all(c.metadata["source"] == "spec-generator-fallback" for c in cases)


def test_adversarial_covers_all_categories_by_default():
    cases = AdversarialGenerator().generate(Case(input="Summarize this.", expectation="A summary."))
    assert {c.metadata["category"] for c in cases} == set(ADVERSARIAL_CATEGORIES)


def test_adversarial_rejects_unknown_category():
    with pytest.raises(ValueError):
        AdversarialGenerator(["totally_made_up_category"])


def test_adversarial_is_category_level_only():
    # Responsible use: every generated case is tagged with a documented category and the
    # deterministic 'adversarial' source — no free-form, novel exploit synthesis.
    cases = AdversarialGenerator().generate(Case(input="hi", expectation="e"))
    for case in cases:
        assert case.metadata["category"] in ADVERSARIAL_CATEGORIES
        assert case.metadata["source"] == "adversarial"


def test_mutation_produces_deterministic_variants():
    cases = Mutator().mutate(Case(input="Hello there", expectation="e", criteria=["x"]), n=4)
    assert len(cases) == 4
    assert "uppercase" in {c.metadata["mutation"] for c in cases}
    assert all(c.metadata["base_input"] == "Hello there" for c in cases)
