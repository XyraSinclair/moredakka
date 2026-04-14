from __future__ import annotations

import json
import secrets
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from moredakka.config import AppConfig, ProviderConfig, _find_config_path
from moredakka.context import ContextPacket
from moredakka.util import ensure_dir, run_command, sha256_json


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def make_invocation_id(started_at: datetime | None = None) -> str:
    stamp = (started_at or utc_now()).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(4)}"


def _git(args: list[str], cwd: Path) -> str | None:
    result = run_command(["git", *args], cwd=cwd)
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def repo_metadata(cwd: Path, *, base_ref: str) -> dict[str, Any]:
    repo_root = _git(["rev-parse", "--show-toplevel"], cwd)
    branch = _git(["branch", "--show-current"], cwd)
    head_sha = _git(["rev-parse", "HEAD"], cwd)
    merge_base = _git(["merge-base", "HEAD", base_ref], cwd) if repo_root else None
    return {
        "cwd": str(cwd),
        "repo_root": repo_root,
        "branch": branch,
        "head_sha": head_sha,
        "base_ref": base_ref,
        "merge_base": merge_base,
    }


def config_metadata(config: AppConfig, *, cwd: Path, explicit_config_path: str | None) -> dict[str, Any]:
    path = _find_config_path(explicit_config_path, cwd)
    config_payload = to_jsonable(config)
    return {
        "config_path": str(path) if path else None,
        "config_hash": sha256_json(config_payload),
        "config": config_payload,
    }


def resolved_run_dir(cwd: Path, run_dir: str) -> Path:
    run_dir_path = Path(run_dir).expanduser()
    return (run_dir_path if run_dir_path.is_absolute() else cwd / run_dir_path).resolve()


def write_run_artifact(*, cwd: Path, run_dir: str, invocation_id: str, artifact: Mapping[str, Any]) -> Path:
    root = ensure_dir(resolved_run_dir(cwd, run_dir))
    dated = ensure_dir(root / invocation_id[:8])
    path = dated / f"{invocation_id}.json"
    path.write_text(json.dumps(to_jsonable(dict(artifact)), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _lookup_number(payload: Mapping[str, Any] | None, *paths: tuple[str, ...]) -> int | None:
    if not payload:
        return None
    for path in paths:
        cur: Any = payload
        found = True
        for key in path:
            if not isinstance(cur, Mapping) or key not in cur:
                found = False
                break
            cur = cur[key]
        if not found or cur is None:
            continue
        if isinstance(cur, bool):
            continue
        if isinstance(cur, (int, float)):
            return int(cur)
    return None


def _lookup_float(payload: Mapping[str, Any] | None, *paths: tuple[str, ...]) -> float | None:
    if not payload:
        return None
    for path in paths:
        cur: Any = payload
        found = True
        for key in path:
            if not isinstance(cur, Mapping) or key not in cur:
                found = False
                break
            cur = cur[key]
        if not found or cur is None:
            continue
        if isinstance(cur, bool):
            continue
        if isinstance(cur, (int, float)):
            return float(cur)
    return None


def normalize_usage(usage: Mapping[str, Any] | None) -> dict[str, Any]:
    usage = dict(usage or {})
    input_tokens = _lookup_number(
        usage,
        ("input_tokens",),
        ("prompt_tokens",),
        ("prompt_token_count",),
        ("cached_content_token_count",),
    )
    output_tokens = _lookup_number(
        usage,
        ("output_tokens",),
        ("completion_tokens",),
        ("candidates_token_count",),
    )
    total_tokens = _lookup_number(
        usage,
        ("total_tokens",),
        ("total_token_count",),
    )
    reasoning_tokens = _lookup_number(
        usage,
        ("output_tokens_details", "reasoning_tokens"),
        ("reasoning_tokens",),
        ("thoughts_token_count",),
    )
    cached_input_tokens = _lookup_number(
        usage,
        ("input_tokens_details", "cached_tokens"),
        ("cached_content_token_count",),
    )
    if total_tokens is None:
        total_tokens = sum(value for value in [input_tokens, output_tokens] if value is not None) or None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cached_input_tokens": cached_input_tokens,
        "provider_reported_cost_usd": _lookup_float(usage, ("cost",), ("total_cost",), ("cost_usd",)),
        "raw": usage or None,
    }


def estimate_cost_usd(usage_summary: Mapping[str, Any], provider_config: ProviderConfig) -> float | None:
    reported = usage_summary.get("provider_reported_cost_usd")
    if isinstance(reported, (int, float)):
        return float(reported)
    input_tokens = usage_summary.get("input_tokens")
    output_tokens = usage_summary.get("output_tokens")
    input_price = provider_config.input_cost_per_million_tokens
    output_price = provider_config.output_cost_per_million_tokens
    if input_tokens is None and output_tokens is None:
        return None
    if input_price is None and output_price is None:
        return None
    cost = 0.0
    if input_tokens is not None and input_price is not None:
        cost += (float(input_tokens) / 1_000_000.0) * input_price
    if output_tokens is not None and output_price is not None:
        cost += (float(output_tokens) / 1_000_000.0) * output_price
    return round(cost, 8)


def accumulate_usage(items: list[Mapping[str, Any]]) -> dict[str, Any]:
    total_input = 0
    total_output = 0
    total_tokens = 0
    total_reasoning = 0
    total_cached_input = 0
    total_cost = 0.0
    saw_input = saw_output = saw_total = saw_reasoning = saw_cached = saw_cost = False
    for item in items:
        value = item.get("input_tokens")
        if isinstance(value, int):
            total_input += value
            saw_input = True
        value = item.get("output_tokens")
        if isinstance(value, int):
            total_output += value
            saw_output = True
        value = item.get("total_tokens")
        if isinstance(value, int):
            total_tokens += value
            saw_total = True
        value = item.get("reasoning_tokens")
        if isinstance(value, int):
            total_reasoning += value
            saw_reasoning = True
        value = item.get("cached_input_tokens")
        if isinstance(value, int):
            total_cached_input += value
            saw_cached = True
        value = item.get("estimated_cost_usd")
        if isinstance(value, (int, float)):
            total_cost += float(value)
            saw_cost = True
    return {
        "input_tokens": total_input if saw_input else None,
        "output_tokens": total_output if saw_output else None,
        "total_tokens": total_tokens if saw_total else None,
        "reasoning_tokens": total_reasoning if saw_reasoning else None,
        "cached_input_tokens": total_cached_input if saw_cached else None,
        "estimated_cost_usd": round(total_cost, 8) if saw_cost else None,
    }


def context_rendering_stats(packet: ContextPacket, rendered_text: str, *, char_budget: int) -> dict[str, Any]:
    sections = [
        packet.diff_excerpt,
        packet.diff_stats,
        *(doc.excerpt for doc in packet.docs),
        *(item.excerpt for item in packet.file_excerpts),
    ]
    original_chars = sum(len(section) for section in sections if section)
    return {
        "char_budget": char_budget,
        "rendered_chars": len(rendered_text),
        "source_excerpt_chars": original_chars,
        "truncated": len(rendered_text) >= char_budget and original_chars > len(rendered_text),
        "doc_count": len(packet.docs),
        "file_excerpt_count": len(packet.file_excerpts),
        "changed_file_count": len(packet.changed_files),
    }
