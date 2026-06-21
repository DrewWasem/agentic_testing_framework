"""A content-addressed, on-disk cache that wraps any provider.

The cache is the whole reason "cost by construction" is testable: an identical
``(model, system, prompt)`` is answered from disk on the second run, so re-running a suite
costs nothing and adds ~no latency. The key is a SHA-256 of the inner model id plus the
system and prompt, and each response is stored as a small JSON file named after the key.

Standard library only: :mod:`hashlib` for the key, :mod:`json` for the on-disk record,
:mod:`os`/:mod:`pathlib` for the directory. It imports no SDK and lives in ``providers/``,
never ``core/`` — it conforms to the provider seam (``name`` + ``complete``) like any other.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .base import Provider


class CachingProvider:
    """Wrap a provider with a content-addressed on-disk cache of its responses.

    On a hit the cached string is returned **without** calling ``inner``. The ``hits`` and
    ``misses`` counters let an outer wrapper tell whether a given ``complete`` actually
    reached the model (a miss) or replayed from disk (a hit) — which is how the metering
    layer charges $0 for cache hits.
    """

    def __init__(self, inner: Provider, cache_dir: str | Path) -> None:
        self.inner = inner
        self.name = inner.name
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def _key(self, system: str, prompt: str) -> str:
        # Length-prefixed framing so the field boundaries are unambiguous even if a field
        # itself contains the separator — a plain NUL-delimited join is collision-able
        # (name="A\0B"+system="C" would equal name="A"+system="B\0C"); this is not.
        digest = hashlib.sha256()
        for part in (self.name, system, prompt):
            encoded = part.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        return digest.hexdigest()

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def complete(self, system: str, prompt: str) -> str:
        key = self._key(system, prompt)
        path = self._path(key)
        if path.exists():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                # A top-level JSON value that isn't an object (null/str/int/list/bool) makes
                # the subscript raise TypeError — catch it so a poisoned file degrades to a
                # miss rather than crashing the run.
                response = record["response"]
            except (OSError, ValueError, KeyError, TypeError):
                response = None
            if isinstance(response, str):
                self.hits += 1
                return response
        # Miss: call inner, persist, return.
        self.misses += 1
        response = self.inner.complete(system, prompt)
        record = {"model": self.name, "system": system, "prompt": prompt, "response": response}
        try:
            path.write_text(json.dumps(record), encoding="utf-8")
        except OSError:
            # A write failure must not break the run — just forfeit the cache for this key.
            pass
        return response

    def reset(self) -> None:
        """Zero the hit/miss counters (the on-disk entries are left in place)."""

        self.hits = 0
        self.misses = 0
