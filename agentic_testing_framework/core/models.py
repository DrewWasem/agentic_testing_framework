"""Model tiering — never hardcode model strings in logic; reference these constants.

The tribunal is cheap by construction: reviewers and the council run on the CHEAP tier,
the generator on MID, and only the orchestrator — where deep reasoning earns its cost —
on the FRONTIER tier.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class Tier(str, Enum):
    CHEAP = "cheap"
    MID = "mid"
    FRONTIER = "frontier"


# Default Anthropic model id per tier — rolling aliases (no date suffix) so each tier
# tracks the latest snapshot of its model. Swap in one place, or override per provider.
DEFAULT_MODELS: dict[Tier, str] = {
    Tier.CHEAP: "claude-haiku-4-5",
    Tier.MID: "claude-sonnet-4-6",
    Tier.FRONTIER: "claude-opus-4-8",
}


class ModelPrice(NamedTuple):
    """USD per one million tokens, split by direction (input vs output)."""

    input_per_mtok: float
    output_per_mtok: float


# Public list prices (USD / 1M tokens), used only to *estimate* cost for the cost rollup.
# These are list prices for estimation, not a bill — keyed by the same dateless ids as
# DEFAULT_MODELS so the price table tracks whatever snapshot each tier currently aliases.
# A model with no entry here (e.g. the offline mock) is treated as free.
PRICES: dict[str, ModelPrice] = {
    DEFAULT_MODELS[Tier.CHEAP]: ModelPrice(1.0, 5.0),
    DEFAULT_MODELS[Tier.MID]: ModelPrice(3.0, 15.0),
    DEFAULT_MODELS[Tier.FRONTIER]: ModelPrice(5.0, 25.0),
}


def price_for(model_id: str | None) -> ModelPrice | None:
    """Return the list price for ``model_id``, or ``None`` if it is unpriced.

    ``None`` means "estimate this as free" — true for the offline mock and for any model
    not in :data:`PRICES`. Cost estimation must treat an unknown model as $0, never guess.
    """

    if model_id is None:
        return None
    return PRICES.get(model_id)
