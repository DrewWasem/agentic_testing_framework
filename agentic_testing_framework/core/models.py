"""Model tiering — never hardcode model strings in logic; reference these constants.

The tribunal is cheap by construction: reviewers and the council run on the CHEAP tier,
the generator on MID, and only the orchestrator — where deep reasoning earns its cost —
on the FRONTIER tier.
"""

from __future__ import annotations

from enum import Enum


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
