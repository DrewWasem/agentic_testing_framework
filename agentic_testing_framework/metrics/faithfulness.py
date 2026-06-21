"""Faithfulness — is every claim in the output supported by the provided context?

Penalizes the output for asserting anything the INPUT/EXPECTATION/CRITERIA do not support.
A higher score means the output stays grounded in what it was given; an output that invents
facts beyond its context scores low.
"""

from __future__ import annotations

from .base import Metric


class Faithfulness(Metric):
    name = "faithfulness"
    scale = 5.0
    threshold = 0.6

    @property
    def instruction(self) -> str:
        return (
            "Measure FAITHFULNESS: how well every claim in the output is supported by the "
            "provided INPUT and EXPECTATION (the context). Penalize any statement that is "
            "not entailed by that context. A fully grounded output scores high; one that "
            "asserts unsupported facts scores low. Quote the least-supported claim as "
            "evidence."
        )
