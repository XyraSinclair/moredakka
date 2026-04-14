from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from moredakka.config import ProviderConfig
from moredakka.providers import build_provider
from moredakka.providers.openrouter_provider import OpenRouterProvider


class OpenRouterProviderTests(unittest.TestCase):
    def _config(self, *, reasoning_effort: str | None = "medium") -> ProviderConfig:
        return ProviderConfig(
            name="openrouter",
            kind="openrouter",
            model="openai/gpt-5.4",
            api_key_env="OPENROUTER_API_KEY",
            reasoning_effort=reasoning_effort,
            base_url="https://openrouter.ai/api/v1",
            app_url="https://example.com",
            app_name="moredakka",
        )

    def test_build_provider_supports_openrouter(self) -> None:
        provider = build_provider(self._config())
        self.assertIsInstance(provider, OpenRouterProvider)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True)
    @patch("openai.OpenAI")
    @patch.object(
        OpenRouterProvider,
        "_fetch_supported_parameters",
        return_value={"reasoning", "response_format", "structured_outputs"},
    )
    def test_generate_json_uses_openrouter_client_and_headers(
        self,
        _mock_supported: MagicMock,
        mock_openai: MagicMock,
    ) -> None:
        response = SimpleNamespace(
            output_text='{"status":"ok"}',
            usage={"total_tokens": 3},
            id="resp_123",
        )
        client = MagicMock()
        client.responses.create.return_value = response
        mock_openai.return_value = client

        provider = OpenRouterProvider(self._config())
        result = provider.generate_json(
            system="system text",
            user="user text",
            schema_name="demo",
            schema={"type": "object"},
        )

        mock_openai.assert_called_once_with(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            timeout=OpenRouterProvider.REQUEST_TIMEOUT_SECONDS,
            default_headers={
                "HTTP-Referer": "https://example.com",
                "X-OpenRouter-Title": "moredakka",
            },
        )
        request = client.responses.create.call_args.kwargs
        self.assertEqual(request["reasoning"], {"effort": "medium"})
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertEqual(result.data, {"status": "ok"})
        self.assertEqual(result.response_id, "resp_123")

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True)
    @patch.object(OpenRouterProvider, "_fetch_supported_parameters", return_value={"reasoning"})
    def test_generate_json_rejects_models_without_structured_outputs(
        self,
        _mock_supported: MagicMock,
    ) -> None:
        provider = OpenRouterProvider(self._config())

        with self.assertRaisesRegex(RuntimeError, "does not support structured outputs"):
            provider.generate_json(
                system="system text",
                user="user text",
                schema_name="demo",
                schema={"type": "object"},
            )

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True)
    @patch.object(
        OpenRouterProvider,
        "_fetch_supported_parameters",
        return_value={"response_format", "structured_outputs"},
    )
    def test_generate_json_rejects_unsupported_reasoning(
        self,
        _mock_supported: MagicMock,
    ) -> None:
        provider = OpenRouterProvider(self._config(reasoning_effort="high"))

        with self.assertRaisesRegex(RuntimeError, "does not support reasoning"):
            provider.generate_json(
                system="system text",
                user="user text",
                schema_name="demo",
                schema={"type": "object"},
            )


if __name__ == "__main__":
    unittest.main()
