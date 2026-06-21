"""Prompt-as-code — every judge/reviewer/orchestrator/generator/metric system prompt
carries a stable id, a version, and a changelog.

A prompt is the thing most likely to change a verdict, so it is treated like code: each
one lives in a single registry with a monotonically-bumped ``version`` and a one-line-per-
entry ``changelog``. The tribunal stages source their system text from here instead of
holding a private string constant, and the pipeline stamps the versions that produced a
ruling onto the :class:`~agentic_testing_framework.core.types.Verdict`. That makes a
verdict reproducible: it states which prompt versions judged it, so a drift after a prompt
edit is attributable rather than mysterious.

The registry ADDS metadata around the existing prompt text — it is not a rewrite. The text
each stage uses is byte-for-byte what it used before; only the version/changelog provenance
is new. Standard-library only.
"""

from __future__ import annotations

from .registry import PROMPTS, Prompt, get_prompt

__all__ = ["PROMPTS", "Prompt", "get_prompt"]
