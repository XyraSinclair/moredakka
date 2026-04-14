from __future__ import annotations

import copy
import json
import urllib.parse
import urllib.request
from typing import Any

from moredakka.config import ProviderConfig
from moredakka.providers.base import ProviderResult
from moredakka.util import env_required, extract_response_output_text, object_to_dict


class OpenRouterProvider:
    supports_previous_response_id = False
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    METADATA_TIMEOUT_SECONDS = 10.0
    REQUEST_TIMEOUT_SECONDS = 30.0

    def __init__(self, config: ProviderConfig) -> None:
        self.name = config.name
        self.model = config.model
        self._config = config
        self._supported_parameters: set[str] | None = None

    def _base_url(self) -> str:
        return (self._config.base_url or self.DEFAULT_BASE_URL).rstrip("/")

    def _default_headers(self) -> dict[str, str] | None:
        headers: dict[str, str] = {}
        if self._config.app_url:
            headers["HTTP-Referer"] = self._config.app_url
        if self._config.app_name:
            headers["X-OpenRouter-Title"] = self._config.app_name
        return headers or None

    def _models_url(self) -> str:
        return urllib.parse.urljoin(self._base_url() + "/", "models?output_modalities=text")

    def _fetch_supported_parameters(self) -> set[str]:
        if self._supported_parameters is not None:
            return self._supported_parameters

        try:
            with urllib.request.urlopen(self._models_url(), timeout=self.METADATA_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch OpenRouter model metadata for {self.model} from {self._models_url()}."
            ) from exc

        for model in payload.get("data", []):
            identifiers = {
                str(model.get("id", "")),
                str(model.get("canonical_slug", "")),
            }
            if self.model not in identifiers:
                continue
            supported = model.get("supported_parameters") or []
            self._supported_parameters = {str(item) for item in supported}
            return self._supported_parameters

        raise RuntimeError(
            f"OpenRouter model metadata for {self.model} was not found in {self._models_url()}."
        )

    def _sanitize_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        sanitized = copy.deepcopy(schema)
        if not self.model.startswith("anthropic/"):
            return sanitized

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") in {"integer", "number"}:
                    node.pop("minimum", None)
                    node.pop("maximum", None)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(sanitized)
        return sanitized

    def _build_request(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        supported = self._fetch_supported_parameters()
        if "structured_outputs" not in supported and "response_format" not in supported:
            raise RuntimeError(
                f"OpenRouter model {self.model} does not support structured outputs; choose a model with "
                f"'structured_outputs' or 'response_format' in supported_parameters."
            )

        request: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": self._sanitize_schema(schema),
                    "strict": True,
                }
            },
        }
        if self._config.reasoning_effort:
            if "reasoning" not in supported:
                raise RuntimeError(
                    f"OpenRouter model {self.model} does not support reasoning; unset reasoning_effort or "
                    f"switch to a model advertising 'reasoning' in supported_parameters."
                )
            request["reasoning"] = {"effort": self._config.reasoning_effort}
        return request

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
        previous_response_id: str | None = None,
    ) -> ProviderResult:
        del previous_response_id
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK not installed. Run: pip install openai"
            ) from exc

        api_key = env_required(self._config.api_key_env)
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": self._base_url(),
            "timeout": self.REQUEST_TIMEOUT_SECONDS,
        }
        headers = self._default_headers()
        if headers:
            client_kwargs["default_headers"] = headers
        client = OpenAI(**client_kwargs)

        response = client.responses.create(
            **self._build_request(
                system=system,
                user=user,
                schema_name=schema_name,
                schema=schema,
            )
        )
        raw_text = extract_response_output_text(response)
        if not raw_text:
            raise RuntimeError("OpenRouter response contained no output_text.")
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenRouter response was not valid JSON:\n{raw_text}") from exc

        return ProviderResult(
            provider=self.name,
            model=self.model,
            data=data,
            raw_text=raw_text,
            response_id=getattr(response, "id", None),
            usage=object_to_dict(getattr(response, "usage", None)),
        )
