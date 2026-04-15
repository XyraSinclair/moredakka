from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Mapping


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture text output."""
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def truncate_middle(text: str, max_chars: int) -> str:
    """Truncate long text while preserving both ends."""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars < 16:
        return text[:max_chars]
    head = max_chars // 2
    tail = max_chars - head - len("\n…\n")
    return f"{text[:head]}\n…\n{text[-tail:]}"


def safe_read_text(path: Path, max_chars: int | None = None) -> str:
    """Read text, returning empty string for unreadable or binary-ish files."""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if b"\x00" in data[:4096]:
        return ""
    text = data.decode("utf-8", errors="ignore")
    if max_chars is not None:
        return truncate_middle(text, max_chars)
    return text


def sha256_json(payload: object) -> str:
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text_atomic(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
    ensure_dir(path.parent)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return path


def find_upward(start: Path, filename: str) -> Path | None:
    for current in (start.resolve(), *start.resolve().parents):
        candidate = current / filename
        if candidate.exists():
            return candidate
    return None


def load_local_env(start: Path, env: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(env or os.environ)
    env_path = find_upward(start, ".env")
    if not env_path:
        return merged
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in merged:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        merged[key] = value
    return merged


def normalize_phrase(text: str) -> str:
    return " ".join(text.lower().split())


def flatten_strings(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    for value in values:
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, dict):
            out.extend(flatten_strings(value.values()))
        elif isinstance(value, (list, tuple, set)):
            out.extend(flatten_strings(value))
    return out


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable not set: {name}")
    return value


def attr_or_key(obj: object, name: str, default: object = None) -> object:
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def object_to_dict(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else None
    if hasattr(value, "to_dict"):
        dumped = value.to_dict()
        return dumped if isinstance(dumped, dict) else None
    if hasattr(value, "items"):
        return dict(value)  # type: ignore[arg-type]
    return None


def extract_response_output_text(response: object) -> str:
    output_text = attr_or_key(response, "output_text", "")
    if isinstance(output_text, str) and output_text:
        return output_text

    chunks: list[str] = []
    output = attr_or_key(response, "output", [])
    if not isinstance(output, list):
        return ""
    for item in output:
        if attr_or_key(item, "type") != "message":
            continue
        content = attr_or_key(item, "content", [])
        if not isinstance(content, list):
            continue
        for part in content:
            if attr_or_key(part, "type") != "output_text":
                continue
            text = attr_or_key(part, "text", "")
            if isinstance(text, str) and text:
                chunks.append(text)
    return "".join(chunks)
