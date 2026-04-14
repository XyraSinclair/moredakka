from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderConfig:
    name: str
    kind: str
    model: str
    api_key_env: str
    reasoning_effort: str | None = None
    base_url: str | None = None
    app_url: str | None = None
    app_name: str | None = None
    input_cost_per_million_tokens: float | None = None
    output_cost_per_million_tokens: float | None = None


@dataclass
class RoleConfig:
    name: str
    provider: str


@dataclass
class DefaultsConfig:
    mode: str = "plan"
    max_rounds: int = 2
    base_ref: str = "main"
    char_budget: int = 24000
    cache_dir: str = ".moredakka/cache"
    run_dir: str = ".moredakka/runs"
    novelty_threshold: float = 0.15
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None
    max_wall_seconds: int | None = None


@dataclass
class AppConfig:
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    roles: dict[str, RoleConfig] = field(default_factory=dict)


SUPPORTED_PROVIDER_KINDS = {"openai", "gemini", "openrouter"}
SUPPORTED_MODES = {"plan", "here", "review", "patch", "loop"}
REQUIRED_ROLE_NAMES = {"planner", "implementer", "breaker", "minimalist", "synthesizer"}
SUPPORTED_REASONING_EFFORTS = {"low", "medium", "high"}


def _default_config() -> AppConfig:
    cfg = AppConfig()
    cfg.providers = {
        "openrouter_planner": ProviderConfig(
            name="openrouter_planner",
            kind="openrouter",
            model="anthropic/claude-opus-4.6",
            api_key_env="OPENROUTER_API_KEY",
            base_url="https://openrouter.ai/api/v1",
            app_name="moredakka",
        ),
        "openrouter_implementer": ProviderConfig(
            name="openrouter_implementer",
            kind="openrouter",
            model="openai/gpt-5.4",
            api_key_env="OPENROUTER_API_KEY",
            reasoning_effort="medium",
            base_url="https://openrouter.ai/api/v1",
            app_name="moredakka",
        ),
        "openrouter_breaker": ProviderConfig(
            name="openrouter_breaker",
            kind="openrouter",
            model="google/gemini-3.1-pro-preview",
            api_key_env="OPENROUTER_API_KEY",
            base_url="https://openrouter.ai/api/v1",
            app_name="moredakka",
        ),
        "openrouter_minimalist": ProviderConfig(
            name="openrouter_minimalist",
            kind="openrouter",
            model="openai/gpt-5.4-mini",
            api_key_env="OPENROUTER_API_KEY",
            reasoning_effort="medium",
            base_url="https://openrouter.ai/api/v1",
            app_name="moredakka",
        ),
        "openrouter_synthesizer": ProviderConfig(
            name="openrouter_synthesizer",
            kind="openrouter",
            model="openai/gpt-5.4",
            api_key_env="OPENROUTER_API_KEY",
            reasoning_effort="medium",
            base_url="https://openrouter.ai/api/v1",
            app_name="moredakka",
        ),
    }
    cfg.roles = {
        "planner": RoleConfig(name="planner", provider="openrouter_planner"),
        "implementer": RoleConfig(name="implementer", provider="openrouter_implementer"),
        "breaker": RoleConfig(name="breaker", provider="openrouter_breaker"),
        "minimalist": RoleConfig(name="minimalist", provider="openrouter_minimalist"),
        "synthesizer": RoleConfig(name="synthesizer", provider="openrouter_synthesizer"),
    }
    return cfg


def _find_config_path(explicit: str | None, cwd: Path) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise RuntimeError(f"Config file not found: {path}")
        return path
    for current in (cwd, *cwd.parents):
        candidate = current / "moredakka.toml"
        if candidate.exists():
            return candidate
    return None


def _merge_dict(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(default)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _validate_config(cfg: AppConfig) -> AppConfig:
    if cfg.defaults.mode not in SUPPORTED_MODES:
        raise RuntimeError(
            f"Unsupported default mode: {cfg.defaults.mode}. Supported modes: {', '.join(sorted(SUPPORTED_MODES))}"
        )
    if cfg.defaults.max_rounds < 1:
        raise RuntimeError("defaults.max_rounds must be at least 1")
    if cfg.defaults.char_budget < 1000:
        raise RuntimeError("defaults.char_budget must be at least 1000")
    if not 0 <= cfg.defaults.novelty_threshold <= 1:
        raise RuntimeError("defaults.novelty_threshold must be between 0 and 1")
    if not cfg.defaults.cache_dir.strip():
        raise RuntimeError("defaults.cache_dir must not be empty")
    if not cfg.defaults.run_dir.strip():
        raise RuntimeError("defaults.run_dir must not be empty")
    if not cfg.defaults.base_ref.strip():
        raise RuntimeError("defaults.base_ref must not be empty")
    if cfg.defaults.max_total_tokens is not None and cfg.defaults.max_total_tokens < 1:
        raise RuntimeError("defaults.max_total_tokens must be at least 1 when set")
    if cfg.defaults.max_cost_usd is not None and cfg.defaults.max_cost_usd < 0:
        raise RuntimeError("defaults.max_cost_usd must be non-negative when set")
    if cfg.defaults.max_wall_seconds is not None and cfg.defaults.max_wall_seconds < 1:
        raise RuntimeError("defaults.max_wall_seconds must be at least 1 when set")

    unknown_kinds = [
        f"{name}={provider.kind}"
        for name, provider in cfg.providers.items()
        if provider.kind not in SUPPORTED_PROVIDER_KINDS
    ]
    if unknown_kinds:
        raise RuntimeError(f"Unsupported provider kind(s): {', '.join(unknown_kinds)}")

    invalid_provider_fields = [
        name
        for name, provider in cfg.providers.items()
        if not provider.model.strip() or not provider.api_key_env.strip()
    ]
    if invalid_provider_fields:
        raise RuntimeError(
            "Provider config(s) must include non-empty model and api_key_env: " + ", ".join(sorted(invalid_provider_fields))
        )

    invalid_reasoning = [
        f"{name}={provider.reasoning_effort}"
        for name, provider in cfg.providers.items()
        if provider.reasoning_effort is not None and provider.reasoning_effort not in SUPPORTED_REASONING_EFFORTS
    ]
    if invalid_reasoning:
        raise RuntimeError(
            "Unsupported reasoning_effort value(s): " + ", ".join(sorted(invalid_reasoning))
        )

    invalid_pricing = [
        name
        for name, provider in cfg.providers.items()
        if (
            provider.input_cost_per_million_tokens is not None and provider.input_cost_per_million_tokens < 0
        )
        or (
            provider.output_cost_per_million_tokens is not None and provider.output_cost_per_million_tokens < 0
        )
    ]
    if invalid_pricing:
        raise RuntimeError(
            "Provider pricing must be non-negative when set: " + ", ".join(sorted(invalid_pricing))
        )

    missing_required_roles = sorted(REQUIRED_ROLE_NAMES - set(cfg.roles))
    if missing_required_roles:
        raise RuntimeError(
            "Missing required role config(s): " + ", ".join(missing_required_roles)
        )

    missing_role_providers = [
        f"{role.name}->{role.provider}"
        for role in cfg.roles.values()
        if role.provider not in cfg.providers
    ]
    if missing_role_providers:
        raise RuntimeError(
            "Role(s) reference undefined provider(s): " + ", ".join(missing_role_providers)
        )

    return cfg


def load_config(*, cwd: Path, explicit_path: str | None = None) -> AppConfig:
    cfg = _default_config()
    path = _find_config_path(explicit_path, cwd)
    if not path:
        return cfg
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    defaults = raw.get("defaults", {})
    cfg.defaults = DefaultsConfig(
        mode=defaults.get("mode", cfg.defaults.mode),
        max_rounds=int(defaults.get("max_rounds", cfg.defaults.max_rounds)),
        base_ref=str(defaults.get("base_ref", cfg.defaults.base_ref)),
        char_budget=int(defaults.get("char_budget", cfg.defaults.char_budget)),
        cache_dir=str(defaults.get("cache_dir", cfg.defaults.cache_dir)),
        run_dir=str(defaults.get("run_dir", cfg.defaults.run_dir)),
        novelty_threshold=float(defaults.get("novelty_threshold", cfg.defaults.novelty_threshold)),
        max_total_tokens=(
            int(defaults["max_total_tokens"])
            if defaults.get("max_total_tokens") is not None
            else cfg.defaults.max_total_tokens
        ),
        max_cost_usd=(
            float(defaults["max_cost_usd"])
            if defaults.get("max_cost_usd") is not None
            else cfg.defaults.max_cost_usd
        ),
        max_wall_seconds=(
            int(defaults["max_wall_seconds"])
            if defaults.get("max_wall_seconds") is not None
            else cfg.defaults.max_wall_seconds
        ),
    )

    raw_providers = raw.get("providers", {})
    for name, defaults_provider in list(cfg.providers.items()):
        merged = _merge_dict(defaults_provider.__dict__, raw_providers.get(name, {}))
        cfg.providers[name] = ProviderConfig(
            name=name,
            kind=str(merged["kind"]),
            model=str(merged["model"]),
            api_key_env=str(merged["api_key_env"]),
            reasoning_effort=merged.get("reasoning_effort"),
            base_url=merged.get("base_url"),
            app_url=merged.get("app_url"),
            app_name=merged.get("app_name"),
            input_cost_per_million_tokens=(
                float(merged["input_cost_per_million_tokens"])
                if merged.get("input_cost_per_million_tokens") is not None
                else None
            ),
            output_cost_per_million_tokens=(
                float(merged["output_cost_per_million_tokens"])
                if merged.get("output_cost_per_million_tokens") is not None
                else None
            ),
        )
    for name, provider_raw in raw_providers.items():
        if name not in cfg.providers:
            cfg.providers[name] = ProviderConfig(
                name=name,
                kind=str(provider_raw["kind"]),
                model=str(provider_raw["model"]),
                api_key_env=str(provider_raw["api_key_env"]),
                reasoning_effort=provider_raw.get("reasoning_effort"),
                base_url=provider_raw.get("base_url"),
                app_url=provider_raw.get("app_url"),
                app_name=provider_raw.get("app_name"),
                input_cost_per_million_tokens=(
                    float(provider_raw["input_cost_per_million_tokens"])
                    if provider_raw.get("input_cost_per_million_tokens") is not None
                    else None
                ),
                output_cost_per_million_tokens=(
                    float(provider_raw["output_cost_per_million_tokens"])
                    if provider_raw.get("output_cost_per_million_tokens") is not None
                    else None
                ),
            )

    raw_roles = raw.get("roles", {})
    for name, defaults_role in list(cfg.roles.items()):
        role_override = raw_roles.get(name, {})
        cfg.roles[name] = RoleConfig(
            name=name,
            provider=str(role_override.get("provider", defaults_role.provider)),
        )
    for name, role_raw in raw_roles.items():
        if name not in cfg.roles:
            cfg.roles[name] = RoleConfig(name=name, provider=str(role_raw["provider"]))

    return _validate_config(cfg)
