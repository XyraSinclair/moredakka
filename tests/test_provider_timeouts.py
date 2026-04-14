from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from moredakka.config import ProviderConfig
from moredakka.providers.gemini_provider import GeminiProvider
from moredakka.providers.openai_provider import OpenAIProvider


class ProviderTimeoutTests(unittest.TestCase):
    def _openai_config(self) -> ProviderConfig:
        return ProviderConfig(
            name="openai",
            kind="openai",
            model="gpt-5.4",
            api_key_env="OPENAI_API_KEY",
            reasoning_effort="medium",
        )

    def _gemini_config(self) -> ProviderConfig:
        return ProviderConfig(
            name="gemini",
            kind="gemini",
            model="gemini-3.1-pro-preview",
            api_key_env="GEMINI_API_KEY",
        )

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    @patch("openai.OpenAI")
    def test_openai_provider_sets_client_timeout(self, mock_openai: MagicMock) -> None:
        response = SimpleNamespace(
            output_text='{"status":"ok"}',
            usage={"total_tokens": 3},
            id="resp_123",
        )
        client = MagicMock()
        client.responses.create.return_value = response
        mock_openai.return_value = client

        provider = OpenAIProvider(self._openai_config())
        provider.generate_json(
            system="system text",
            user="user text",
            schema_name="demo",
            schema={"type": "object"},
        )

        mock_openai.assert_called_once_with(
            api_key="test-key",
            timeout=OpenAIProvider.REQUEST_TIMEOUT_SECONDS,
        )

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True)
    @patch("google.genai.Client")
    def test_gemini_provider_sets_client_timeout(self, mock_client: MagicMock) -> None:
        response = SimpleNamespace(text='{"status":"ok"}', usage_metadata=None)
        client = MagicMock()
        client.models.generate_content.return_value = response
        mock_client.return_value = client

        provider = GeminiProvider(self._gemini_config())
        provider.generate_json(
            system="system text",
            user="user text",
            schema_name="demo",
            schema={"type": "object"},
        )

        mock_client.assert_called_once_with(
            api_key="test-key",
            http_options={"timeout": GeminiProvider.REQUEST_TIMEOUT_SECONDS},
        )


if __name__ == "__main__":
    unittest.main()
