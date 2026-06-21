"""Hallucination — an inverse metric: how much fabricated/unsupported content is present?

The model scores the *amount* of hallucination (high = lots of fabrication), and the base
flips that, so the normalized 0..1 score reads the same direction as every other metric: a
clean, grounded output scores near 1.0, a fabricating one near 0.0.
"""

from __future__ import annotations

from .base import Metric


class Hallucination(Metric):
    name = "hallucination"
    scale = 5.0
    threshold = 0.6
    higher_is_worse = True

    @property
    def instruction(self) -> str:
        return (
            "Measure HALLUCINATION: the degree to which the output contains fabricated or "
            "unsupported content that contradicts or goes beyond the provided context. "
            "Score HIGH when there is a lot of fabrication and LOW when the output is fully "
            "grounded -- this is an inverse metric. Quote the most clearly fabricated span as "
            "evidence (or note that none was found)."
        )
