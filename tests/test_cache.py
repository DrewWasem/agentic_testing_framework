"""Content-addressed on-disk cache: hits skip the inner call and persist across instances."""

from agentic_testing_framework import CachingProvider


class _SpyProvider:
    """A minimal provider that records every inner call so a cache HIT is observable."""

    name = "spy"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        return f"response#{self.calls}"


def test_identical_call_is_served_from_disk_without_calling_inner(tmp_path):
    spy = _SpyProvider()
    cache = CachingProvider(spy, tmp_path)
    first = cache.complete("sys", "prompt")
    assert spy.calls == 1
    assert cache.misses == 1
    assert cache.hits == 0
    # Second identical (system, prompt) replays from disk — no new inner call.
    second = cache.complete("sys", "prompt")
    assert second == first
    assert spy.calls == 1  # inner was NOT called again
    assert cache.hits == 1
    assert cache.misses == 1


def test_different_prompts_miss_separately(tmp_path):
    spy = _SpyProvider()
    cache = CachingProvider(spy, tmp_path)
    a = cache.complete("sys", "prompt-a")
    b = cache.complete("sys", "prompt-b")
    assert a != b
    assert spy.calls == 2
    assert cache.misses == 2
    assert cache.hits == 0
    # Differing system also misses.
    cache.complete("other-sys", "prompt-a")
    assert spy.calls == 3
    assert cache.misses == 3


def test_a_fresh_provider_over_the_same_dir_reads_the_prior_run(tmp_path):
    spy_one = _SpyProvider()
    first = CachingProvider(spy_one, tmp_path).complete("sys", "prompt")
    assert spy_one.calls == 1
    # A brand-new CachingProvider with a brand-new inner over the SAME dir hits on disk.
    spy_two = _SpyProvider()
    cache_two = CachingProvider(spy_two, tmp_path)
    replayed = cache_two.complete("sys", "prompt")
    assert replayed == first
    assert spy_two.calls == 0  # the second inner was never called — served from disk
    assert cache_two.hits == 1
    assert cache_two.misses == 0


def test_constructs_with_a_nonexistent_dir(tmp_path):
    missing = tmp_path / "does" / "not" / "exist"
    assert not missing.exists()
    cache = CachingProvider(_SpyProvider(), missing)
    assert missing.exists()
    cache.complete("s", "p")
    assert any(missing.iterdir())  # an entry was written


def test_reset_zeros_counters_but_keeps_disk_entries(tmp_path):
    spy = _SpyProvider()
    cache = CachingProvider(spy, tmp_path)
    cache.complete("s", "p")
    cache.reset()
    assert cache.hits == 0
    assert cache.misses == 0
    # The on-disk entry survives reset — a subsequent identical call still hits.
    cache.complete("s", "p")
    assert cache.hits == 1
    assert spy.calls == 1


def test_corrupt_cache_file_degrades_to_miss_not_crash(tmp_path):
    # A poisoned cache file (top-level JSON that isn't an object, or non-JSON) must degrade
    # to a miss, never crash. Regression for the uncaught TypeError on record["response"].
    spy = _SpyProvider()
    cache = CachingProvider(spy, tmp_path)
    cache.complete("s", "p")  # writes one valid cache file
    cache_file = next(tmp_path.glob("*.json"))
    poisons = ("null", "42", '"a bare string"', "[1, 2, 3]", "true", "not json {{{", "")
    base = spy.calls
    for i, poison in enumerate(poisons, start=1):
        cache_file.write_text(poison, encoding="utf-8")
        out = cache.complete("s", "p")  # must NOT raise
        assert isinstance(out, str) and out
        assert spy.calls == base + i  # degraded to a miss → inner was called again
