from __future__ import annotations

import json
import unittest
import threading
import tempfile
from pathlib import Path
from unittest.mock import patch

from moredakka.errors import MoreDakkaRuntimeError

from moredakka.config import AppConfig, DefaultsConfig, ProviderConfig, RoleConfig
from moredakka.query_language import compile_query_plan, render_query_plan_summary, render_selected_ops
from moredakka.context import ContextPacket
from moredakka.orchestrator import (
    _global_system_prompt,
    _role_user_prompt,
    _synthesis_prompt,
    estimate_novelty,
    run_workflow,
)
from moredakka.providers.base import ProviderResult
from moredakka.schemas import role_analysis_schema, schema_name_for_profile
from moredakka.util import sha256_json


class _BarrierProvider:
    supports_previous_response_id = False
    barrier = threading.Barrier(2, timeout=1)

    def __init__(self, name: str) -> None:
        self.name = name
        self.model = f"{name}-model"

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, object],
        previous_response_id: str | None = None,
    ) -> ProviderResult:
        del system, schema, previous_response_id
        if schema_name.startswith("moredakka_role_analysis"):
            type(self).barrier.wait()
            role = "unknown"
            marker = "ROLE\n"
            if marker in user:
                role = user.split(marker, 1)[1].split("\n", 1)[0].strip() or role
            data = {
                "role": role,
                "focus": "focus",
                "one_sentence_take": "take",
                "observations": [],
                "top_problems": [],
                "candidate_paths": [],
                "recommended_steps": [],
                "tests": [],
                "risks": [],
                "edits": [],
                "assumptions": [],
                "questions": [],
                "stop_conditions": [],
                "confidence": 0.5,
            }
        else:
            data = {
                "inferred_objective": "objective",
                "one_sentence_take": "take",
                "selected_path": {
                    "name": "path",
                    "summary": "summary",
                    "tradeoffs": [],
                },
                "top_problems": [],
                "next_actions": [],
                "commit_plan": [],
                "tests": [],
                "edit_targets": [],
                "major_risks": [],
                "disagreements": [],
                "stop_conditions": [],
                "open_questions": [],
                "operator_summary": None,
                "handoff_paragraph": None,
                "status_ledger": None,
                "intent_card": None,
                "confidence": 0.5,
                "confidence_rationale": "ok",
            }
        return ProviderResult(
            provider=self.name,
            model=self.model,
            data=data,
            raw_text="{}",
            response_id=None,
            usage=None,
        )


class _BudgetProvider:
    supports_previous_response_id = False

    def __init__(self, name: str) -> None:
        self.name = name
        self.model = f"{name}-model"

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, object],
        previous_response_id: str | None = None,
    ) -> ProviderResult:
        del system, user, schema, previous_response_id
        if not schema_name.startswith("moredakka_role_analysis"):
            raise AssertionError("synthesis should not run after budget stop")
        return ProviderResult(
            provider=self.name,
            model=self.model,
            data={
                "role": "planner",
                "focus": "focus",
                "one_sentence_take": "take",
                "observations": [],
                "top_problems": [],
                "candidate_paths": [],
                "recommended_steps": [],
                "tests": [],
                "risks": [],
                "edits": [],
                "assumptions": [],
                "questions": [],
                "stop_conditions": [],
                "confidence": 0.5,
            },
            raw_text="{}",
            response_id=None,
            usage={"total_tokens": 999, "input_tokens": 600, "output_tokens": 399},
        )


class _LowNoveltyProvider:
    supports_previous_response_id = False

    def __init__(self, name: str) -> None:
        self.name = name
        self.model = f"{name}-model"

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, object],
        previous_response_id: str | None = None,
    ) -> ProviderResult:
        del system, user, schema, previous_response_id
        if schema_name.startswith("moredakka_role_analysis"):
            data = {
                "role": "planner",
                "focus": "focus",
                "one_sentence_take": "steady state",
                "observations": [],
                "top_problems": [{"title": "same issue", "detail": "same detail"}],
                "candidate_paths": [],
                "recommended_steps": [{"title": "same step", "why": "same why"}],
                "tests": [],
                "risks": [{"name": "same risk", "mitigation": "same mitigation"}],
                "edits": [],
                "assumptions": [],
                "questions": [],
                "stop_conditions": [],
                "confidence": 0.5,
            }
        else:
            data = {
                "inferred_objective": "objective",
                "one_sentence_take": "take",
                "selected_path": {"name": "path", "summary": "summary", "tradeoffs": []},
                "top_problems": [],
                "next_actions": [],
                "commit_plan": [],
                "tests": [],
                "edit_targets": [],
                "major_risks": [],
                "disagreements": [],
                "stop_conditions": [],
                "open_questions": [],
                "operator_summary": None,
                "handoff_paragraph": None,
                "status_ledger": None,
                "intent_card": None,
                "confidence": 0.5,
                "confidence_rationale": "ok",
            }
        return ProviderResult(
            provider=self.name,
            model=self.model,
            data=data,
            raw_text="{}",
            response_id=None,
            usage=None,
        )


class PromptCompilationTests(unittest.TestCase):
    def test_role_prompt_includes_directive_and_compiled_plan(self) -> None:
        user_prompt = _role_user_prompt(
            mode="plan",
            objective="objective",
            role_name="planner",
            context_text="context",
            round_index=1,
            directive="be critical and keep it tight",
            query_plan_summary="- critique\n- condense",
            selected_ops_text="critique condense",
        )

        self.assertIn("DIRECTIVE PROSE\nbe critical and keep it tight", user_prompt)
        self.assertIn("SELECTED OPERATIONS\ncritique condense", user_prompt)
        self.assertIn("COMPILED PLAN\n- critique\n- condense", user_prompt)

    def test_synthesis_prompt_includes_final_artifact_obligations(self) -> None:
        synthesis_prompt = _synthesis_prompt(
            mode="plan",
            objective="objective",
            context_text="context",
            round_summaries="ROUND 1\n...",
            directive="continue but first tell me what remains",
            query_plan_summary="- resume\n- close",
            selected_ops_text="resume close",
            final_artifact_text="status_ledger\noperator_summary",
        )

        self.assertIn("DIRECTIVE PROSE\ncontinue but first tell me what remains", synthesis_prompt)
        self.assertIn("FINAL ARTIFACT OBLIGATIONS\nstatus_ledger\noperator_summary", synthesis_prompt)


class NoveltyTests(unittest.TestCase):
    def test_estimate_novelty_detects_change(self) -> None:
        prev_round = [
            {
                "one_sentence_take": "Do the auth fix first.",
                "top_problems": [{"title": "refresh race"}],
                "recommended_steps": [{"title": "patch refresh"}],
                "risks": [{"name": "token loss"}],
                "tests": [{"name": "refresh integration"}],
            }
        ]
        cur_round = [
            {
                "one_sentence_take": "Do the auth fix first, then add retry caps.",
                "top_problems": [{"title": "refresh race"}, {"title": "retry storm"}],
                "recommended_steps": [{"title": "patch refresh"}, {"title": "cap retries"}],
                "risks": [{"name": "token loss"}],
                "tests": [{"name": "refresh integration"}, {"name": "retry backoff"}],
            }
        ]
        novelty = estimate_novelty(prev_round, cur_round)
        self.assertGreater(novelty, 0)

    def test_estimate_novelty_zero_for_empty_round(self) -> None:
        self.assertEqual(estimate_novelty([], []), 0.0)

    @patch("moredakka.orchestrator.render_context_packet", return_value="context")
    @patch("moredakka.orchestrator.build_context_packet")
    @patch("moredakka.orchestrator.default_role_sequence", return_value=["planner", "implementer"])
    @patch("moredakka.orchestrator.build_provider")
    @patch("moredakka.orchestrator.load_config")
    def test_run_workflow_runs_role_rounds_in_parallel(
        self,
        mock_load_config: unittest.mock.MagicMock,
        mock_build_provider: unittest.mock.MagicMock,
        mock_default_role_sequence: unittest.mock.MagicMock,
        mock_build_context_packet: unittest.mock.MagicMock,
        mock_render_context_packet: unittest.mock.MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                defaults=DefaultsConfig(max_rounds=1, cache_dir=".moredakka/cache"),
                providers={
                    "openai": ProviderConfig(
                        name="openai",
                        kind="openai",
                        model="gpt-5.4",
                        api_key_env="OPENAI_API_KEY",
                        reasoning_effort="medium",
                    )
                },
                roles={
                    "planner": RoleConfig(name="planner", provider="openai"),
                    "implementer": RoleConfig(name="implementer", provider="openai"),
                    "synthesizer": RoleConfig(name="synthesizer", provider="openai"),
                },
            )
            packet = ContextPacket(
                cwd=str(root),
                repo_root=str(root),
                mode="plan",
                objective="",
                inferred_objective="objective",
                base_ref="main",
                branch=None,
            )
            mock_load_config.return_value = config
            mock_build_provider.side_effect = lambda provider_cfg: _BarrierProvider(provider_cfg.name)
            mock_build_context_packet.return_value = packet
            mock_render_context_packet.return_value = "context"

            result = run_workflow(
                cwd=root,
                mode="plan",
                objective=None,
                rounds=1,
                use_cache=False,
            )

        self.assertEqual(len(result.rounds), 1)
        self.assertEqual({item["role"] for item in result.rounds[0]}, {"planner", "implementer"})
        self.assertEqual(result.synthesis["inferred_objective"], "objective")
        self.assertTrue(result.run_artifact_path)
        self.assertEqual(result.run_artifact["invocation"]["run_status"], "success")
        self.assertEqual(result.run_artifact["invocation"]["stop_reason"], "max_rounds")
        self.assertIn("usage_totals", result.run_artifact)
        self.assertEqual(result.run_artifact["provider_roster"][-1], "synthesizer: openai/openai-model")
        self.assertEqual(result.run_artifact["query_compilation"]["selected_ops"], [])

    @patch("moredakka.orchestrator.render_context_packet", return_value="context")
    @patch("moredakka.orchestrator.build_context_packet")
    @patch("moredakka.orchestrator.default_role_sequence", return_value=["planner"])
    @patch("moredakka.orchestrator.build_provider")
    @patch("moredakka.orchestrator.load_config")
    def test_run_workflow_degrades_before_synthesis_when_budget_exceeded(
        self,
        mock_load_config: unittest.mock.MagicMock,
        mock_build_provider: unittest.mock.MagicMock,
        _mock_default_role_sequence: unittest.mock.MagicMock,
        mock_build_context_packet: unittest.mock.MagicMock,
        _mock_render_context_packet: unittest.mock.MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                defaults=DefaultsConfig(max_rounds=2, cache_dir=".moredakka/cache", max_total_tokens=100),
                providers={
                    "openai": ProviderConfig(
                        name="openai",
                        kind="openai",
                        model="gpt-5.4",
                        api_key_env="OPENAI_API_KEY",
                    )
                },
                roles={
                    "planner": RoleConfig(name="planner", provider="openai"),
                    "synthesizer": RoleConfig(name="synthesizer", provider="openai"),
                },
            )
            packet = ContextPacket(
                cwd=str(root),
                repo_root=str(root),
                mode="plan",
                objective="",
                inferred_objective="objective",
                base_ref="main",
                branch=None,
            )
            mock_load_config.return_value = config
            mock_build_provider.side_effect = lambda provider_cfg: _BudgetProvider(provider_cfg.name)
            mock_build_context_packet.return_value = packet

            result = run_workflow(
                cwd=root,
                mode="plan",
                objective=None,
                rounds=2,
                use_cache=False,
            )

        self.assertEqual(result.run_artifact["invocation"]["run_status"], "degraded")
        self.assertEqual(result.run_artifact["invocation"]["stop_reason"], "max_total_tokens")
        self.assertEqual(result.synthesis["selected_path"]["name"], "bounded-stop")
        self.assertEqual(result.provider_notes, ["planner: openai/openai-model"])

    @patch("moredakka.orchestrator.render_context_packet", return_value="context")
    @patch("moredakka.orchestrator.build_context_packet")
    @patch("moredakka.orchestrator.build_provider")
    @patch("moredakka.orchestrator.load_config")
    def test_run_workflow_compiles_directive_and_adds_operator_artifacts(
        self,
        mock_load_config: unittest.mock.MagicMock,
        mock_build_provider: unittest.mock.MagicMock,
        mock_build_context_packet: unittest.mock.MagicMock,
        _mock_render_context_packet: unittest.mock.MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                defaults=DefaultsConfig(max_rounds=1, cache_dir=".moredakka/cache"),
                providers={
                    "openai": ProviderConfig(
                        name="openai",
                        kind="openai",
                        model="gpt-5.4",
                        api_key_env="OPENAI_API_KEY",
                    )
                },
                roles={
                    "planner": RoleConfig(name="planner", provider="openai"),
                    "implementer": RoleConfig(name="implementer", provider="openai"),
                    "breaker": RoleConfig(name="breaker", provider="openai"),
                    "minimalist": RoleConfig(name="minimalist", provider="openai"),
                    "synthesizer": RoleConfig(name="synthesizer", provider="openai"),
                },
            )
            packet = ContextPacket(
                cwd=str(root),
                repo_root=str(root),
                mode="plan",
                objective="",
                inferred_objective="objective",
                base_ref="main",
                branch=None,
            )
            mock_load_config.return_value = config
            mock_build_provider.side_effect = lambda provider_cfg: _LowNoveltyProvider(provider_cfg.name)
            mock_build_context_packet.return_value = packet

            result = run_workflow(
                cwd=root,
                mode="plan",
                objective=None,
                directive="continue from where we were, but first tell me what remains and keep it tight",
                rounds=1,
                use_cache=False,
            )

        self.assertEqual(result.run_artifact["query_compilation"]["selected_ops"], ["resume", "close", "condense"])
        self.assertIsInstance(result.run_artifact["query_compilation"]["query_plan"]["context_policy"], dict)
        self.assertIn("operator_summary", result.synthesis)
        self.assertIn("status_ledger", result.synthesis)
        self.assertIn("remaining", result.synthesis["status_ledger"])

    @patch("moredakka.orchestrator.render_context_packet", return_value="context")
    @patch("moredakka.orchestrator.build_context_packet")
    @patch("moredakka.orchestrator.default_role_sequence", return_value=["planner"])
    @patch("moredakka.orchestrator.build_provider")
    @patch("moredakka.orchestrator.load_config")
    def test_run_workflow_stops_on_low_novelty_and_still_runs_synthesis(
        self,
        mock_load_config: unittest.mock.MagicMock,
        mock_build_provider: unittest.mock.MagicMock,
        _mock_default_role_sequence: unittest.mock.MagicMock,
        mock_build_context_packet: unittest.mock.MagicMock,
        _mock_render_context_packet: unittest.mock.MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                defaults=DefaultsConfig(max_rounds=2, cache_dir=".moredakka/cache", novelty_threshold=0.5),
                providers={
                    "openai": ProviderConfig(
                        name="openai",
                        kind="openai",
                        model="gpt-5.4",
                        api_key_env="OPENAI_API_KEY",
                    )
                },
                roles={
                    "planner": RoleConfig(name="planner", provider="openai"),
                    "synthesizer": RoleConfig(name="synthesizer", provider="openai"),
                },
            )
            packet = ContextPacket(
                cwd=str(root),
                repo_root=str(root),
                mode="plan",
                objective="",
                inferred_objective="objective",
                base_ref="main",
                branch=None,
            )
            mock_load_config.return_value = config
            mock_build_provider.side_effect = lambda provider_cfg: _LowNoveltyProvider(provider_cfg.name)
            mock_build_context_packet.return_value = packet

            result = run_workflow(cwd=root, mode="plan", objective=None, rounds=2, use_cache=False)

        self.assertEqual(len(result.rounds), 2)
        self.assertEqual(result.run_artifact["invocation"]["stop_reason"], "low_novelty")
        self.assertEqual(result.run_artifact["invocation"]["run_status"], "success")
        self.assertEqual(result.provider_notes[-1], "synthesizer: openai/openai-model")

    def test_run_workflow_persists_failed_invocations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text("[defaults]\nmode = 'invalid'\n", encoding="utf-8")

            with self.assertRaises(MoreDakkaRuntimeError) as ctx:
                run_workflow(cwd=root, mode="plan", objective=None, use_cache=False)

            self.assertTrue(ctx.exception.run_artifact_path)
            run_files = sorted((root / ".moredakka" / "runs").rglob("*.json"))
            self.assertTrue(run_files)
            payload = json.loads(run_files[-1].read_text(encoding="utf-8"))
            self.assertEqual(payload["invocation"]["run_status"], "failed")
            self.assertEqual(payload["invocation"]["stop_reason"], "error")
            self.assertEqual(payload["error"]["type"], "RuntimeError")

    @patch("moredakka.orchestrator.render_context_packet", return_value="context")
    @patch("moredakka.orchestrator.build_context_packet")
    @patch("moredakka.orchestrator.default_role_sequence", return_value=["planner"])
    @patch("moredakka.orchestrator.build_provider")
    @patch("moredakka.orchestrator.load_config")
    def test_run_workflow_ignores_corrupt_cache_entry(
        self,
        mock_load_config: unittest.mock.MagicMock,
        mock_build_provider: unittest.mock.MagicMock,
        _mock_default_role_sequence: unittest.mock.MagicMock,
        mock_build_context_packet: unittest.mock.MagicMock,
        _mock_render_context_packet: unittest.mock.MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                defaults=DefaultsConfig(max_rounds=1, cache_dir=".moredakka/cache"),
                providers={
                    "openai": ProviderConfig(
                        name="openai",
                        kind="openai",
                        model="gpt-5.4",
                        api_key_env="OPENAI_API_KEY",
                    )
                },
                roles={
                    "planner": RoleConfig(name="planner", provider="openai"),
                    "synthesizer": RoleConfig(name="synthesizer", provider="openai"),
                },
            )
            packet = ContextPacket(
                cwd=str(root),
                repo_root=str(root),
                mode="plan",
                objective="",
                inferred_objective="objective",
                base_ref="main",
                branch=None,
            )
            mock_load_config.return_value = config
            mock_build_provider.side_effect = lambda provider_cfg: _LowNoveltyProvider(provider_cfg.name)
            mock_build_context_packet.return_value = packet

            cache_dir = root / ".moredakka" / "cache"
            cache_dir.mkdir(parents=True)
            system = _global_system_prompt()
            plan = compile_query_plan(mode="plan", directive=None, base_role_names=["planner"], packet=packet)
            user_prompt = _role_user_prompt(
                mode="plan",
                objective="objective",
                role_name="planner",
                context_text="context",
                round_index=1,
                peer_summaries="",
                directive="",
                query_plan_summary=render_query_plan_summary(plan),
                selected_ops_text=render_selected_ops(plan),
            )
            cache_key = sha256_json(
                {
                    "provider": "openai",
                    "model": "openai-model",
                    "system": system,
                    "user": user_prompt,
                    "schema_name": schema_name_for_profile("moredakka_role_analysis", "software"),
                    "schema": role_analysis_schema("software"),
                    "previous_response_id": None,
                }
            )
            (cache_dir / f"{cache_key}.json").write_text("{not-json", encoding="utf-8")

            result = run_workflow(cwd=root, mode="plan", objective=None, rounds=1, use_cache=True)

            self.assertEqual(result.run_artifact["invocation"]["run_status"], "success")
            self.assertTrue(list(cache_dir.glob("*.corrupt")))


if __name__ == "__main__":
    unittest.main()
