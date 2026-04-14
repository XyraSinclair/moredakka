from __future__ import annotations

import unittest

from moredakka.config import ProviderConfig
from moredakka.providers.openrouter_provider import OpenRouterProvider


class OpenRouterSchemaSanitizationTests(unittest.TestCase):
    def _provider(self, model: str) -> OpenRouterProvider:
        return OpenRouterProvider(
            ProviderConfig(
                name="openrouter_test",
                kind="openrouter",
                model=model,
                api_key_env="OPENROUTER_API_KEY",
                reasoning_effort=None,
                base_url="https://openrouter.ai/api/v1",
                app_name="moredakka",
            )
        )

    def test_anthropic_schema_strips_numeric_bounds(self) -> None:
        provider = self._provider("anthropic/claude-sonnet-4.5")
        schema = {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "name": {"type": "string"},
            },
            "required": ["score", "confidence", "name"],
            "additionalProperties": False,
        }

        sanitized = provider._sanitize_schema(schema)

        self.assertEqual(sanitized["properties"]["score"]["type"], "integer")
        self.assertNotIn("minimum", sanitized["properties"]["score"])
        self.assertNotIn("maximum", sanitized["properties"]["score"])
        self.assertEqual(sanitized["properties"]["confidence"]["type"], "number")
        self.assertNotIn("minimum", sanitized["properties"]["confidence"])
        self.assertNotIn("maximum", sanitized["properties"]["confidence"])

    def test_openai_schema_preserves_numeric_bounds(self) -> None:
        provider = self._provider("openai/gpt-5.4")
        schema = {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
            },
            "required": ["score"],
            "additionalProperties": False,
        }

        sanitized = provider._sanitize_schema(schema)

        self.assertEqual(sanitized["properties"]["score"]["minimum"], 0)
        self.assertEqual(sanitized["properties"]["score"]["maximum"], 10)


if __name__ == "__main__":
    unittest.main()
