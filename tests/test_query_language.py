from __future__ import annotations

import unittest

from moredakka.context import ContextPacket
from moredakka.query_language import compile_query_plan


class QueryLanguageTests(unittest.TestCase):
    def test_compile_query_plan_infers_resume_close_condense(self) -> None:
        plan = compile_query_plan(
            mode="plan",
            directive="continue from where we were, but first tell me what remains and keep it tight",
        )

        self.assertEqual(plan.selected_ops, ["resume", "close", "condense"])
        self.assertIn("resume", [item.canonical_op for item in plan.candidate_operations])
        self.assertIn("close", [item.canonical_op for item in plan.candidate_operations])
        self.assertIn("condense", [item.canonical_op for item in plan.candidate_operations])
        self.assertIn("status_ledger", plan.final_artifacts)
        self.assertIn("operator_summary", plan.final_artifacts)

    def test_compile_query_plan_infers_diverse_compare_flow(self) -> None:
        plan = compile_query_plan(
            mode="plan",
            directive="what actually matters here? give me multiple angles, compare options, and then pick one",
        )

        self.assertEqual(plan.selected_ops, ["intent", "branch", "compare", "integrate"])
        self.assertEqual(plan.objective_strategy, "extract_intent_then_plan")
        self.assertTrue(plan.synthesis_policy.require_candidate_comparison)

    def test_compile_query_plan_infers_options_from_more_natural_prose(self) -> None:
        plan = compile_query_plan(
            mode="plan",
            directive="what actually matters here; give me options and tighten the answer",
        )

        self.assertEqual(plan.selected_ops, ["intent", "branch", "condense"])

    def test_compile_query_plan_uses_mode_biases(self) -> None:
        review_plan = compile_query_plan(mode="review", directive=None)
        patch_plan = compile_query_plan(mode="patch", directive=None)

        self.assertIn("critique", review_plan.selected_ops)
        self.assertIn("minimal", patch_plan.selected_ops)

    def test_compile_query_plan_uses_packet_context_signals(self) -> None:
        packet = ContextPacket(
            cwd="/tmp/demo",
            repo_root="/tmp/demo",
            mode="review",
            objective="",
            inferred_objective="objective",
            base_ref="main",
            branch="feature/demo",
            changed_files=["src/demo.py"],
            diff_excerpt="diff --git a/src/demo.py b/src/demo.py",
        )
        plan = compile_query_plan(mode="review", directive=None, packet=packet)

        self.assertIn("local", plan.selected_ops)
        self.assertIn("has_diff", plan.context_signals)
        self.assertIn("changed_files=1", plan.context_signals)

    def test_compile_query_plan_uses_recent_run_artifact_signal(self) -> None:
        plan = compile_query_plan(
            mode="plan",
            directive="continue",
            has_recent_run_artifact=True,
        )

        self.assertIn("recent_run_artifact", plan.context_signals)
        self.assertIn("resume", plan.selected_ops)

    def test_compile_query_plan_digests_recent_run_summary(self) -> None:
        plan = compile_query_plan(
            mode="plan",
            directive=None,
            has_recent_run_artifact=True,
            recent_run_summary={
                "run_status": "degraded",
                "stop_reason": "max_total_tokens",
                "selected_ops": ["branch", "compare"],
            },
        )

        self.assertIn("recent_run_status=degraded", plan.context_signals)
        self.assertIn("recent_stop_reason=max_total_tokens", plan.context_signals)
        self.assertIn("critique", plan.selected_ops)
        self.assertIn("close", plan.selected_ops)
        self.assertIn("handoff", plan.selected_ops)
        self.assertIn("integrate", plan.selected_ops)

    def test_compile_query_plan_softens_handoff_without_prior_run_state(self) -> None:
        plan = compile_query_plan(mode="plan", directive="handoff")
        statuses = {item.canonical_op: item.status for item in plan.candidate_operations}
        self.assertEqual(statuses["handoff"], "rejected")

    def test_compile_query_plan_downranks_conflicting_resume_and_fresh(self) -> None:
        plan = compile_query_plan(
            mode="plan",
            directive="start fresh and do not continue the last run, but also continue from where we were",
        )

        statuses = {item.canonical_op: item.status for item in plan.candidate_operations}
        self.assertEqual(statuses["fresh"], "selected")
        self.assertEqual(statuses["resume"], "rejected")
        self.assertEqual(plan.selected_ops, ["fresh"])


if __name__ == "__main__":
    unittest.main()
