from __future__ import annotations

import argparse
import sys
from pathlib import Path

import os

from moredakka.doctor import render_doctor_json, render_doctor_markdown, run_doctor
from moredakka.orchestrator import run_workflow
from moredakka.report import render_json, render_markdown
from moredakka.surface_registry import resolve_surface_adapter
from moredakka.util import load_local_env


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moredakka",
        description="Run a bounded multi-model plan-improvement loop over the current problem surface.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--objective", type=str, default=None, help="Explicit objective override.")
        subparser.add_argument(
            "--ask",
            "--directive",
            dest="directive",
            type=str,
            default=None,
            help="Free-prose directive that the query compiler should translate into bounded orchestration operations.",
        )
        subparser.add_argument("--config", type=str, default=None, help="Path to moredakka.toml")
        subparser.add_argument("--surface", type=str, default=None, help="Problem surface adapter to use.")
        subparser.add_argument(
            "--schema-profile",
            type=str,
            default=None,
            help="Structured output profile to use (auto, software, generic).",
        )
        subparser.add_argument("--base-ref", type=str, default=None, help="Base ref for review mode.")
        subparser.add_argument("--rounds", type=int, default=None, help="Max role-critique rounds.")
        subparser.add_argument("--char-budget", type=int, default=None, help="Max chars for packed context.")
        subparser.add_argument("--no-cache", action="store_true", help="Disable local response caching.")
        subparser.add_argument(
            "--format",
            choices=["markdown", "json"],
            default="markdown",
            help="Stdout format.",
        )
        subparser.add_argument(
            "--write-prefix",
            type=str,
            default=None,
            help="Write report files to <prefix>.md and <prefix>.json in addition to stdout.",
        )

    for name in ["here", "plan", "review", "patch", "loop"]:
        sp = subparsers.add_parser(name)
        add_common(sp)

    doctor = subparsers.add_parser("doctor", help="Run bootstrap and environment checks.")
    doctor.add_argument("--config", type=str, default=None, help="Path to moredakka.toml")
    doctor.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Stdout format.",
    )

    pack = subparsers.add_parser("pack", help="Print only the packed local context.")
    pack.add_argument("--objective", type=str, default=None)
    pack.add_argument("--surface", type=str, default="repo")
    pack.add_argument("--base-ref", type=str, default="main")
    pack.add_argument("--char-budget", type=int, default=24000)
    pack.add_argument("--mode", choices=["plan", "review", "patch", "loop", "here"], default="plan")
    return parser


def _write_reports(prefix: str, markdown: str, json_text: str) -> None:
    prefix_path = Path(prefix)
    prefix_path.parent.mkdir(parents=True, exist_ok=True)
    prefix_path.with_suffix(".md").write_text(markdown, encoding="utf-8")
    prefix_path.with_suffix(".json").write_text(json_text, encoding="utf-8")


def _emit_cli_error(message: str, *, hint: str | None = None) -> int:
    sys.stderr.write(f"error: {message}\n")
    if hint:
        sys.stderr.write(f"hint: {hint}\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cwd = Path.cwd()
    os.environ.update(load_local_env(cwd))

    try:
        if args.command == "doctor":
            report = run_doctor(cwd=cwd, config_path=args.config)
            output = render_doctor_markdown(report) if args.format == "markdown" else render_doctor_json(report)
            sys.stdout.write(output)
            return 0 if report.ok else 1

        if args.command == "pack":
            surface_adapter = resolve_surface_adapter(args.surface)
            surface, packet = surface_adapter.build_surface(
                cwd=cwd,
                mode=args.mode,
                objective=args.objective,
                base_ref=args.base_ref,
                char_budget=args.char_budget,
            )
            sys.stdout.write(render_json(packet=packet, surface=surface, synthesis={}, rounds=[], provider_notes=[]))
            return 0

        mode = "plan" if args.command == "here" else args.command
        rounds = args.rounds
        if args.command == "here" and rounds is None:
            rounds = 1
        result = run_workflow(
            cwd=cwd,
            mode=mode,
            objective=args.objective,
            directive=getattr(args, "directive", None),
            config_path=args.config,
            surface_name=getattr(args, "surface", None),
            schema_profile=getattr(args, "schema_profile", None),
            base_ref=args.base_ref,
            rounds=rounds,
            char_budget=args.char_budget,
            use_cache=not args.no_cache,
        )
    except RuntimeError as exc:
        message = str(exc).strip() or "command failed"
        run_artifact_path = getattr(exc, "run_artifact_path", None)
        hint = None
        if "base ref" in message:
            hint = "run `moredakka doctor` or pass `--base-ref <existing-ref>`"
        elif "Required environment variable not set" in message:
            hint = "set the missing environment variable in your shell or repo-local .env, then rerun `moredakka doctor`"
        elif "Config" in message or "config" in message:
            hint = "fix moredakka.toml or pass `--config <valid-path>`"
        if run_artifact_path:
            hint = (hint + "; " if hint else "") + f"inspect run artifact at {run_artifact_path}"
        return _emit_cli_error(message, hint=hint)

    run_artifact = getattr(result, "run_artifact", None)
    run_artifact_path = getattr(result, "run_artifact_path", None)
    markdown = render_markdown(
        packet=result.surface,
        synthesis=result.synthesis,
        rounds=result.rounds,
        provider_notes=result.provider_notes,
        run_artifact=run_artifact,
        run_artifact_path=run_artifact_path,
    )
    json_text = render_json(
        packet=result.packet,
        surface=result.surface,
        synthesis=result.synthesis,
        rounds=result.rounds,
        provider_notes=result.provider_notes,
        run_artifact=run_artifact,
        run_artifact_path=run_artifact_path,
    )

    if args.write_prefix:
        _write_reports(args.write_prefix, markdown, json_text)

    sys.stdout.write(markdown if args.format == "markdown" else json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
