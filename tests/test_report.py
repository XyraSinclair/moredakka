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

    def test_report_surfaces_query_compilation_and_operator_artifacts(self) -> None:
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
            "query_compilation": {
                "directive": "continue, but first tell me what remains and keep it tight",
                "selected_ops": ["resume", "close", "condense"],
                "candidate_operations": [
                    {
                        "canonical_op": "resume",
                        "score": 0.9,
                        "evidence": ["continue"],
                        "rationale": "resume cue",
                        "status": "selected",
                    },
                    {
                        "canonical_op": "close",
                        "score": 0.8,
                        "evidence": ["what remains"],
                        "rationale": "closure cue",
                        "status": "selected",
                    },
                ],
                "query_plan": {
                    "objective_strategy": "continue_with_status_first",
                    "final_artifacts": ["status_ledger", "operator_summary"],
                },
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
            "operator_summary": "Short operator summary.",
            "status_ledger": {
                "done": ["inspected latest state"],
                "remaining": ["pick next safe step"],
                "blocked": [],
                "next": ["execute the highest-leverage change"],
            },
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

        self.assertIn("continue, but first tell me what remains", markdown)
        self.assertIn("resume, close, condense", markdown)
        self.assertIn("Short operator summary.", markdown)
        self.assertIn("inspected latest state", markdown)
        self.assertEqual(payload["synthesis"]["operator_summary"], "Short operator summary.")
        self.assertEqual(payload["run"]["query_compilation"]["selected_ops"], ["resume", "close", "condense"])


if __name__ == "__main__":
    unittest.main()
