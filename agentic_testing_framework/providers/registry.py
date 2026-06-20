"""Resolve providers by name. The Anthropic factory imports the SDK only when called,
so the registry (and the package) stay dependency-free until a real SDK backend is used.
The Claude-CLI provider needs no SDK (just ``subprocess``), so it is registered directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import Provider
from .claude_cli import ClaudeCLIProvider
from .mock import MockProvider


def _make_anthropic(**kwargs: Any) -> Provider:
    from .anthropic import AnthropicProvider  # lazy: SDK imported only here

    return AnthropicProvider(**kwargs)


_REGISTRY: dict[str, Callable[..., Provider]] = {
    "mock": MockProvider,
    "claude-cli": ClaudeCLIProvider,
    "anthropic": _make_anthropic,
}


def register_provider(name: str, factory: Callable[..., Provider]) -> None:
    """Register a provider factory under ``name``."""

    _REGISTRY[name] = factory


def get_provider(name: str, **kwargs: Any) -> Provider:
    """Construct a provider by registered name, passing ``kwargs`` to its factory."""

    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise KeyError(f"Unknown provider {name!r}. Known: {sorted(_REGISTRY)}") from None
    return factory(**kwargs)
