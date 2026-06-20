"""Tolerant JSON extraction for model output.

Models wrap JSON in prose or ``` fences, and prose can contain stray braces. This tries
fenced blocks first, then scans for the first *balanced* ``{...}`` span that actually
parses as a JSON object — so a stray brace in surrounding prose no longer defeats it.
Fails loudly with :class:`JSONParseError` only when there genuinely is no JSON object.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class JSONParseError(ValueError):
    """Raised when model output cannot be parsed into a JSON object."""


def _first_balanced_object(text: str) -> dict[str, Any] | None:
    """Return the first balanced ``{...}`` span in ``text`` that parses to a dict.

    Tracks string literals and escapes so braces inside JSON strings don't throw off the
    depth count. Spans that don't parse (e.g. a stray ``{`` in prose) are skipped.
    """

    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    parsed = json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    start = -1
                    continue
                if isinstance(parsed, dict):
                    return parsed
                start = -1
    return None


def extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from ``text`` (fenced blocks first, then anywhere)."""

    candidates = [match.group(1) for match in _FENCE.finditer(text)]
    candidates.append(text)
    for candidate in candidates:
        found = _first_balanced_object(candidate)
        if found is not None:
            return found
    raise JSONParseError(f"No JSON object found in model output: {text[:200]!r}")
