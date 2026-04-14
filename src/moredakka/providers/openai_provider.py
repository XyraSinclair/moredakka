from __future__ import annotations

import json
from typing import Any

from moredakka.config import ProviderConfig
from moredakka.providers.base import ProviderResult
from moredakka.util import env_required, extract_response_output_text, object_to_dict


class OpenAIProvider:
    supports_previous_response_id = True
    REQUEST_TIMEOUT_SECONDS = 30.0

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
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK not installed. Run: pip install openai"
            ) from exc

        api_key = env_required(self._config.api_key_env)
        client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": self.REQUEST_TIMEOUT_SECONDS}
        if self._config.base_url:
            client_kwargs["base_url"] = self._config.base_url
        client = OpenAI(**client_kwargs)

        text_config: dict[str, Any] = {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        }
        request: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "text": text_config,
        }
        if self._config.reasoning_effort:
            request["reasoning"] = {"effort": self._config.reasoning_effort}
        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        response = client.responses.create(**request)
        raw_text = extract_response_output_text(response)
        if not raw_text:
            raise RuntimeError("OpenAI response contained no output_text.")
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenAI response was not valid JSON:\n{raw_text}") from exc

        usage = object_to_dict(getattr(response, "usage", None))

        return ProviderResult(
            provider=self.name,
            model=self.model,
            data=data,
            raw_text=raw_text,
            response_id=getattr(response, "id", None),
            usage=usage,
        )
