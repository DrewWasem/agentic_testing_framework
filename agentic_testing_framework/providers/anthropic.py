"""A real provider backed by Anthropic's API.

The SDK is imported lazily inside :meth:`complete`, so importing this module — or the
whole package — never requires ``anthropic`` to be installed. This is what keeps the
core dependency-free while still allowing a one-line swap to a live judge.
"""

from __future__ import annotations

from ..core.models import DEFAULT_MODELS, Tier


class AnthropicProvider:
    """Talk to a Claude model. Defaults to the MID tier; the pipeline wires cheaper or
    more capable tiers per stage.
    """

    name = "anthropic"

    def __init__(
        self,
        model: str | None = None,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        api_key: str | None = None,
    ) -> None:
        self.model = model or DEFAULT_MODELS[Tier.MID]
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._api_key = api_key

    def complete(self, system: str, prompt: str) -> str:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "The 'anthropic' SDK is not installed. Install the optional extra: "
                "pip install 'agentic-testing-framework[anthropic]'"
            ) from exc

        client = (
            anthropic.Anthropic(api_key=self._api_key) if self._api_key else anthropic.Anthropic()
        )
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [
            getattr(block, "text", "")
            for block in message.content
            if getattr(block, "type", "") == "text"
        ]
        return "".join(parts)
