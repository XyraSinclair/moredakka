from __future__ import annotations

import unittest

from moredakka.schemas import minimal_shape_ok, role_analysis_schema, synthesis_schema


class SchemaTests(unittest.TestCase):
    def test_software_role_schema_has_required_fields(self) -> None:
        schema = role_analysis_schema("software")
        self.assertIn("required", schema)
        self.assertIn("top_problems", schema["required"])
        self.assertIn("recommended_steps", schema["required"])
        self.assertIn("observations", schema["properties"])

    def test_generic_role_schema_has_required_fields(self) -> None:
        schema = role_analysis_schema("generic")
        self.assertIn("recommended_actions", schema["required"])
        self.assertIn("validation_checks", schema["required"])
        self.assertNotIn("edits", schema["required"])

    def test_software_synthesis_schema_has_required_fields(self) -> None:
        schema = synthesis_schema("software")
        self.assertIn("selected_path", schema["required"])
        self.assertIn("commit_plan", schema["required"])
        self.assertNotIn("operator_summary", schema["required"])
        self.assertNotIn("status_ledger", schema["required"])
        self.assertNotIn("intent_card", schema["required"])
        self.assertIn("operator_summary", schema["properties"])

    def test_generic_synthesis_schema_has_required_fields(self) -> None:
        schema = synthesis_schema("generic")
        self.assertIn("validation_checks", schema["required"])
        self.assertNotIn("commit_plan", schema["required"])

    def test_minimal_shape_ok_for_software_role(self) -> None:
        role_payload = {
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
        }
        self.assertTrue(minimal_shape_ok(role_payload, synthesis=False, profile="software"))

    def test_minimal_shape_ok_for_generic_synthesis_without_optional_artifacts(self) -> None:
        payload = {
            "inferred_objective": "objective",
            "one_sentence_take": "take",
            "selected_path": {"name": "path", "summary": "summary", "tradeoffs": []},
            "top_problems": [],
            "next_actions": [],
            "validation_checks": [],
            "major_risks": [],
            "disagreements": [],
            "stop_conditions": [],
            "open_questions": [],
            "confidence": 0.5,
            "confidence_rationale": "ok",
        }
        self.assertTrue(minimal_shape_ok(payload, synthesis=True, profile="generic"))


if __name__ == "__main__":
    unittest.main()
