from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ProviderResult:
    provider: str
    model: str
    data: dict[str, Any]
    raw_text: str
    response_id: str | None = None
    usage: dict[str, Any] | None = None


class Provider(Protocol):
    name: str
    model: str
    supports_previous_response_id: bool

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
        previous_response_id: str | None = None,
    ) -> ProviderResult:
        ...
