from __future__ import annotations

import json
from typing import Any

from moredakka.config import ProviderConfig
from moredakka.providers.base import ProviderResult
from moredakka.util import env_required


class GeminiProvider:
    supports_previous_response_id = False
    REQUEST_TIMEOUT_SECONDS = 30

    def __init__(self, config: ProviderConfig) -> None:
        self.name = config.name
        self.model = config.model
        self._config = config

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
        previous_response_id: str | None = None,
    ) -> ProviderResult:
        del schema_name, previous_response_id
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "Google GenAI SDK not installed. Run: pip install google-genai"
            ) from exc

        api_key = env_required(self._config.api_key_env)
        client = genai.Client(api_key=api_key, http_options={"timeout": self.REQUEST_TIMEOUT_SECONDS})
        response = client.models.generate_content(
            model=self.model,
            contents=f"{system}\n\n{user}",
            config={
                "response_mime_type": "application/json",
                "response_json_schema": schema,
            },
        )
        raw_text = getattr(response, "text", "")
        if not raw_text:
            raise RuntimeError("Gemini response contained no text.")
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gemini response was not valid JSON:\n{raw_text}") from exc

        usage_metadata = getattr(response, "usage_metadata", None)
        usage = None
        if usage_metadata is not None:
            usage = (
                usage_metadata.to_dict()
                if hasattr(usage_metadata, "to_dict")
                else dict(usage_metadata)
                if hasattr(usage_metadata, "items")
                else None
            )

        return ProviderResult(
            provider=self.name,
            model=self.model,
            data=data,
            raw_text=raw_text,
            usage=usage,
        )
