from __future__ import annotations

from moredakka.config import ProviderConfig
from moredakka.providers.gemini_provider import GeminiProvider
from moredakka.providers.openai_provider import OpenAIProvider
from moredakka.providers.openrouter_provider import OpenRouterProvider


def build_provider(config: ProviderConfig):
    if config.kind == "openai":
        return OpenAIProvider(config)
    if config.kind == "gemini":
        return GeminiProvider(config)
    if config.kind == "openrouter":
        return OpenRouterProvider(config)
    raise ValueError(f"Unsupported provider kind: {config.kind}")
