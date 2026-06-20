"""Error paths for the target adapters: cli non-zero exit, http error wrapping, SSRF guard."""

import json
import sys
import urllib.error

import pytest

from agentic_testing_framework import CliTarget, HttpTarget


def test_cli_target_nonzero_exit_raises():
    target = CliTarget([sys.executable, "-c", "import sys; sys.exit(3)"])
    with pytest.raises(RuntimeError, match="exited 3"):
        target.run("anything")


def test_http_target_wraps_http_error(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.HTTPError("http://x/run", 500, "Server Error", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(RuntimeError, match="500"):
        HttpTarget("http://x/run").run("q")


def test_http_target_wraps_url_error(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(RuntimeError, match="unreachable"):
        HttpTarget("http://x/run").run("q")


def test_http_target_blocks_resolved_private_host_when_enabled():
    target = HttpTarget(
        "http://internal.example/run",
        block_private_hosts=True,
        resolver=lambda host: ["10.0.0.5"],
    )
    with pytest.raises(RuntimeError, match="private"):
        target.run("q")


def test_http_target_blocks_loopback_literal_when_enabled():
    with pytest.raises(RuntimeError, match="private"):
        HttpTarget("http://127.0.0.1:9000/run", block_private_hosts=True).run("q")


def test_http_target_is_permissive_by_default(monkeypatch):
    # The common case — testing a local agent — must keep working with the guard off.
    class FakeResponse:
        def __init__(self, body):
            self._body = body.encode("utf-8")

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: FakeResponse(json.dumps({"output": "ok"})),
    )
    assert HttpTarget("http://127.0.0.1:8080/run").run("q") == "ok"  # not blocked


def test_http_target_blocks_localhost_name_when_enabled():
    with pytest.raises(RuntimeError, match="local host"):
        HttpTarget("http://localhost:8080/run", block_private_hosts=True).run("q")


def test_http_target_blocks_dot_local_name_when_enabled():
    with pytest.raises(RuntimeError, match="local host"):
        HttpTarget("http://myagent.local/run", block_private_hosts=True).run("q")


def test_http_target_blocks_octal_obfuscated_loopback_when_enabled():
    # "0177.0.0.1" is octal 127.0.0.1 — ipaddress rejects it but inet_aton resolves it.
    with pytest.raises(RuntimeError, match="private"):
        HttpTarget("http://0177.0.0.1/run", block_private_hosts=True).run("q")


def test_http_target_blocks_decimal_obfuscated_loopback_when_enabled():
    # 2130706433 == 127.0.0.1 as a single decimal integer.
    with pytest.raises(RuntimeError, match="private"):
        HttpTarget("http://2130706433/run", block_private_hosts=True).run("q")


def test_http_target_unresolvable_host_raises_clean_error_when_enabled():
    def boom(host):
        raise OSError("nodename nor servname provided")

    target = HttpTarget("http://nope.invalid/run", block_private_hosts=True, resolver=boom)
    with pytest.raises(RuntimeError, match="resolve"):
        target.run("q")
