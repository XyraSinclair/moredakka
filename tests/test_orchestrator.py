from __future__ import annotations

import unittest
import threading
import tempfile
from pathlib import Path
from unittest.mock import patch

from moredakka.config import AppConfig, DefaultsConfig, ProviderConfig, RoleConfig
from moredakka.context import ContextPacket
from moredakka.orchestrator import run_workflow
from moredakka.providers.base import ProviderResult

from moredakka.orchestrator import estimate_novelty


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
        if schema_name == "moredakka_role_analysis":
            type(self).barrier.wait()
            role = "unknown"
            marker = "ROLE\n"
            if marker in user:
                role = user.split(marker, 1)[1].split("\n", 1)[0].strip() or role
            data = {
                "role": role,
                "focus": "focus",
                "one_sentence_take": "take",
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


if __name__ == "__main__":
    unittest.main()
