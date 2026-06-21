"""Answer relevancy — does the output actually address the input that was asked?

Independent of correctness: an answer can be factually true yet off-topic. A higher score
means the output is on-point for the INPUT; a digression or non-answer scores low.
"""

from __future__ import annotations

from .base import Metric


class AnswerRelevancy(Metric):
    name = "answer_relevancy"
    scale = 5.0
    threshold = 0.6

    @property
    def instruction(self) -> str:
        return (
            "Measure ANSWER RELEVANCY: how directly the output addresses the INPUT that was "
            "asked. Judge relevance only, not factual correctness -- a true but off-topic "
            "answer is still irrelevant. An output that fully and directly answers the input "
            "scores high; a digression, partial answer, or non-answer scores low. Quote the "
            "part of the output that bears most (or least) on the input as evidence."
        )
