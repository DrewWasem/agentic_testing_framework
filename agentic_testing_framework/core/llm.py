"""One small helper that every LLM-backed stage shares: call a provider, parse JSON,
retry once with a stricter nudge if the output wasn't valid JSON.

Kept separate so the tribunal stages and the generator don't each reimplement the
call/parse/retry loop. Callers decide how to degrade on failure (raise vs. fallback).
"""

from __future__ import annotations

from typing import Any

from ..providers.base import Provider
from .parsing import JSONParseError, extract_json


def complete_json(
    provider: Provider,
    system: str,
    prompt: str,
    *,
    max_retries: int = 1,
) -> dict[str, Any]:
    """Call ``provider.complete`` and parse the result as a JSON object.

    On a parse failure, retries up to ``max_retries`` times with a stricter instruction.
    Raises :class:`JSONParseError` if every attempt fails.
    """

    last: JSONParseError | None = None
    for attempt in range(max_retries + 1):
        text = prompt if attempt == 0 else f"{prompt}\n\nReturn ONLY a valid JSON object, no prose."
        raw = provider.complete(system, text)
        try:
            return extract_json(raw)
        except JSONParseError as exc:
            last = exc
    raise last if last is not None else JSONParseError("empty response")
