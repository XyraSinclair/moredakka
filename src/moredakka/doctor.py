from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

from moredakka.config import AppConfig, _default_config, _find_config_path, load_config
from moredakka.runlog import resolved_run_dir
from moredakka.util import ensure_dir, load_local_env, run_command


@dataclass
class DoctorCheck:
    name: str
    status: str
    summary: str
    detail: str = ""
    fix: str = ""


@dataclass
class DoctorReport:
    ok: bool
    cwd: str
    config_path: str | None
    checks: list[DoctorCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "cwd": self.cwd,
            "config_path": self.config_path,
            "checks": [asdict(check) for check in self.checks],
        }


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _writable_dir_check(path: Path, *, name: str, fix: str) -> DoctorCheck:
    try:
        ensure_dir(path)
        probe = path / ".doctor-write-test"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
        return DoctorCheck(
            name=name,
            status="pass",
            summary=("Cache directory is writable." if name == "cache_dir" else "Run artifact directory is writable."),
            detail=str(path),
        )
    except OSError as exc:
        return DoctorCheck(
            name=name,
            status="fail",
            summary=("Cache directory is not writable." if name == "cache_dir" else "Run artifact directory is not writable."),
            detail=f"{path}: {exc}",
            fix=fix,
        )


def _provider_check(
    *,
    provider_name: str,
    provider_kind: str,
    env_var: str,
    env: Mapping[str, str],
    active: bool,
    module_available: Callable[[str], bool],
) -> DoctorCheck:
    module_name = {
        "openai": "openai",
        "gemini": "google.genai",
        "openrouter": "openai",
    }[provider_kind]
    sdk_ok = module_available(module_name)
    key_ok = bool(env.get(env_var))

    issues: list[str] = []
    if not sdk_ok:
        issues.append(f"missing SDK module {module_name}")
    if not key_ok:
        issues.append(f"missing env {env_var}")

    if not issues:
        return DoctorCheck(
            name=f"provider:{provider_name}",
            status="pass",
            summary=f"{provider_name} is ready.",
            detail=f"kind={provider_kind} env={env_var}",
        )

    status = "fail" if active else "warn"
    fix_parts: list[str] = []
    if not sdk_ok:
        package = "google-genai" if provider_kind == "gemini" else "openai"
        fix_parts.append(f"install {package}")
    if not key_ok:
        fix_parts.append(f"export {env_var}")
    role_text = "active in the current role map" if active else "configured but not active by default"
    return DoctorCheck(
        name=f"provider:{provider_name}",
        status=status,
        summary=f"{provider_name} is not fully ready.",
        detail=f"{role_text}; " + ", ".join(issues),
        fix="; ".join(fix_parts),
    )


def _roster_diversity_check(config: AppConfig) -> DoctorCheck:
    active_models = {
        config.providers[role.provider].model
        for role in config.roles.values()
        if role.provider in config.providers
    }
    if len(active_models) >= 2:
        return DoctorCheck(
            name="roster_diversity",
            status="pass",
            summary="Active role roster uses multiple model families.",
            detail=", ".join(sorted(active_models)),
        )
    only = next(iter(active_models), "(none)")
    return DoctorCheck(
        name="roster_diversity",
        status="warn",
        summary="Active role roster collapses to one model.",
        detail=only,
        fix="Map at least one critical role to a contrast model or provider.",
    )


def _git(args: list[str], cwd: Path) -> str:
    result = run_command(["git", *args], cwd=cwd)
    if result.returncode != 0:
        return ""
    return result.stdout.rstrip("\n")


def _repo_check(cwd: Path, *, git_available: bool, base_ref: str) -> tuple[DoctorCheck, DoctorCheck]:
    if not git_available:
        return (
            DoctorCheck(name="repo", status="warn", summary="Repository checks skipped because git is unavailable."),
            DoctorCheck(name="base_ref", status="warn", summary="Base ref check skipped because git is unavailable."),
        )

    repo_root = _git(["rev-parse", "--show-toplevel"], cwd)
    if not repo_root:
        return (
            DoctorCheck(
                name="repo",
                status="warn",
                summary="Current directory is not inside a git repo.",
                fix="Run moredakka inside a git repo for review-oriented workflows.",
            ),
            DoctorCheck(
                name="base_ref",
                status="warn",
                summary="Base ref not checked outside a git repo.",
            ),
        )

    if not _git(["rev-parse", "--verify", base_ref], cwd):
        return (
            DoctorCheck(name="repo", status="pass", summary="Current directory is inside a git repo.", detail=repo_root),
            DoctorCheck(
                name="base_ref",
                status="fail",
                summary="Configured base ref does not resolve locally.",
                detail=base_ref,
                fix="Fetch the ref, set defaults.base_ref, or pass --base-ref explicitly.",
            ),
        )

    return (
        DoctorCheck(name="repo", status="pass", summary="Current directory is inside a git repo.", detail=repo_root),
        DoctorCheck(name="base_ref", status="pass", summary="Base ref resolves locally.", detail=base_ref),
    )


def run_doctor(
    *,
    cwd: Path,
    config_path: str | None = None,
    env: Mapping[str, str] | None = None,
    version_info: Sequence[int] | None = None,
    which: Callable[[str], str | None] | None = None,
    module_available: Callable[[str], bool] | None = None,
) -> DoctorReport:
    env_map = load_local_env(cwd, env=env)
    version = tuple(version_info or sys.version_info)
    which_fn = which or shutil.which
    module_ok = module_available or _module_available
    resolved_cwd = cwd.resolve()

    checks: list[DoctorCheck] = []

    if version >= (3, 11):
        checks.append(
            DoctorCheck(
                name="python",
                status="pass",
                summary="Python version is supported.",
                detail=".".join(str(part) for part in version[:3]),
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="python",
                status="fail",
                summary="Python 3.11+ is required.",
                detail=".".join(str(part) for part in version[:3]),
                fix="Use bin/moredakka or a Python 3.11+ interpreter.",
            )
        )

    git_path = which_fn("git")
    git_available = bool(git_path)
    if git_path:
        checks.append(
            DoctorCheck(
                name="git",
                status="pass",
                summary="git is available.",
                detail=git_path,
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="git",
                status="fail",
                summary="git is not available on PATH.",
                fix="Install git and ensure it is on PATH.",
            )
        )

    discovered_config = _find_config_path(config_path, resolved_cwd)
    config = _default_config()
    try:
        config = load_config(cwd=resolved_cwd, explicit_path=config_path)
        checks.append(
            DoctorCheck(
                name="config",
                status="pass",
                summary="Configuration loaded.",
                detail=str(discovered_config) if discovered_config else "using built-in defaults",
            )
        )
    except RuntimeError as exc:
        checks.append(
            DoctorCheck(
                name="config",
                status="fail",
                summary="Configuration could not be loaded.",
                detail=str(exc),
                fix="Fix moredakka.toml or pass --config with a valid file.",
            )
        )

    repo_check, base_ref_check = _repo_check(resolved_cwd, git_available=git_available, base_ref=config.defaults.base_ref)
    checks.extend([repo_check, base_ref_check])

    cache_dir_config = Path(config.defaults.cache_dir).expanduser()
    cache_dir = (cache_dir_config if cache_dir_config.is_absolute() else resolved_cwd / cache_dir_config).resolve()
    checks.append(_writable_dir_check(cache_dir, name="cache_dir", fix="Set defaults.cache_dir to a writable path."))

    run_dir = resolved_run_dir(resolved_cwd, config.defaults.run_dir)
    checks.append(_writable_dir_check(run_dir, name="run_dir", fix="Set defaults.run_dir to a writable path."))

    active_provider_names = {role.provider for role in config.roles.values()}
    for provider_name, provider in config.providers.items():
        checks.append(
            _provider_check(
                provider_name=provider_name,
                provider_kind=provider.kind,
                env_var=provider.api_key_env,
                env=env_map,
                active=provider_name in active_provider_names,
                module_available=module_ok,
            )
        )

    checks.append(_roster_diversity_check(config))

    ok = all(check.status != "fail" for check in checks)
    return DoctorReport(
        ok=ok,
        cwd=str(resolved_cwd),
        config_path=str(discovered_config) if discovered_config else None,
        checks=checks,
    )


def render_doctor_markdown(report: DoctorReport) -> str:
    status_line = "PASS" if report.ok else "FAIL"
    lines = [
        "# moredakka doctor",
        "",
        f"overall: {status_line}",
        f"cwd: {report.cwd}",
        f"config: {report.config_path or 'built-in defaults'}",
        "",
        "## checks",
    ]
    for check in report.checks:
        lines.append(f"- [{check.status}] {check.name}: {check.summary}")
        if check.detail:
            lines.append(f"  detail: {check.detail}")
        if check.fix:
            lines.append(f"  fix: {check.fix}")
    return "\n".join(lines).strip() + "\n"


def render_doctor_json(report: DoctorReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"
