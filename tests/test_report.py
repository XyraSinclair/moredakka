from __future__ import annotations

import json
import unittest

from moredakka.context import ContextPacket
from moredakka.report import render_json, render_markdown


class ReportTests(unittest.TestCase):
    def test_report_surfaces_run_metadata_and_usage(self) -> None:
        packet = ContextPacket(
            cwd="/tmp/demo",
            repo_root="/tmp/demo",
            mode="plan",
            objective="",
            inferred_objective="objective",
            base_ref="main",
            branch="feature/demo",
        )
        run_artifact = {
            "invocation": {
                "invocation_id": "demo-run",
                "run_status": "success",
                "stop_reason": "max_rounds",
                "started_at": "2026-04-14T12:00:00Z",
                "duration_ms": 321,
            },
            "repo": {
                "head_sha": "abc123",
                "merge_base": "def456",
            },
            "usage_totals": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "estimated_cost_usd": 0.01,
            },
            "context_rendering": {
                "char_budget": 2000,
                "rendered_chars": 1500,
                "source_excerpt_chars": 3000,
                "truncated": True,
            },
        }
        synthesis = {
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
            "confidence": 0.5,
            "confidence_rationale": "ok",
        }

        markdown = render_markdown(
            packet=packet,
            synthesis=synthesis,
            rounds=[],
            provider_notes=["planner: openrouter/gpt"],
            run_artifact=run_artifact,
            run_artifact_path="/tmp/run.json",
        )
        payload = json.loads(
            render_json(
                packet=packet,
                synthesis=synthesis,
                rounds=[],
                provider_notes=["planner: openrouter/gpt"],
                run_artifact=run_artifact,
                run_artifact_path="/tmp/run.json",
            )
        )

        self.assertIn("invocation_id=demo-run", markdown)
        self.assertIn("estimated_cost_usd=0.01", markdown)
        self.assertEqual(payload["run"]["invocation"]["invocation_id"], "demo-run")
        self.assertEqual(payload["run_artifact_path"], "/tmp/run.json")


if __name__ == "__main__":
    unittest.main()
