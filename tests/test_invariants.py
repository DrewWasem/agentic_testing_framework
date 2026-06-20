"""Small invariant checks: model-id hygiene and the whitespace-tolerant finding-id regex."""

import json

from agentic_testing_framework import Tier
from agentic_testing_framework.core.models import DEFAULT_MODELS
from agentic_testing_framework.providers.mock import _FINDING_ID, _auto_orchestrator


def test_default_models_are_dateless_aliases_for_every_tier():
    assert set(DEFAULT_MODELS) == set(Tier)
    for model_id in DEFAULT_MODELS.values():
        tail = model_id.rsplit("-", 1)[-1]
        assert not (tail.isdigit() and len(tail) == 8), f"{model_id} is date-pinned"


def test_finding_id_regex_tolerates_whitespace_in_source():
    assert _FINDING_ID.findall("[clerk:word_count#0] and [score check#3]") == [
        "clerk:word_count#0",
        "score check#3",
    ]


def test_auto_orchestrator_cites_spaced_source_ids():
    prompt = "EVIDENCE LEDGER:\n[score check#0] score check (info): ok\n"
    data = json.loads(_auto_orchestrator(prompt))
    assert "score check#0" in data["cited_findings"]
