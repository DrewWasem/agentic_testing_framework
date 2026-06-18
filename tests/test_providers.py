"""Provider seam: mock scripting, counting wrapper, registry."""

import json

import pytest

from agentic_testing_framework import CountingProvider, MockProvider, get_provider
from agentic_testing_framework.core.roles import ROLE_ORCHESTRATOR, role_header


def test_mock_scripted_queue():
    mock = MockProvider(["a", "b"])
    assert mock.complete("s", "p") == "a"
    assert mock.complete("s", "p") == "b"
    assert mock.call_count == 2


def test_mock_handler_and_default():
    assert MockProvider(handler=lambda s, p: p.upper()).complete("s", "hi") == "HI"
    assert MockProvider(default="D").complete("s", "p") == "D"


def test_mock_auto_is_role_aware():
    mock = MockProvider()
    out = mock.complete(role_header(ROLE_ORCHESTRATOR), "p")
    assert json.loads(out)["outcome"] == "pass"


def test_counting_provider():
    inner = MockProvider(default="x")
    counter = CountingProvider(inner)
    counter.complete("s", "p")
    counter.complete("s", "p")
    assert counter.calls == 2
    assert counter.name == inner.name
    counter.reset()
    assert counter.calls == 0


def test_registry_resolves_and_rejects():
    assert isinstance(get_provider("mock"), MockProvider)
    with pytest.raises(KeyError):
        get_provider("does-not-exist")
