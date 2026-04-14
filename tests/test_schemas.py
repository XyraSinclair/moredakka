from __future__ import annotations

import unittest

from moredakka.schemas import minimal_shape_ok, role_analysis_schema, synthesis_schema


class SchemaTests(unittest.TestCase):
    def test_role_schema_has_required_fields(self) -> None:
        schema = role_analysis_schema()
        self.assertIn("required", schema)
        self.assertIn("top_problems", schema["required"])
        self.assertIn("recommended_steps", schema["required"])

    def test_synthesis_schema_has_required_fields(self) -> None:
        schema = synthesis_schema()
        self.assertIn("selected_path", schema["required"])
        self.assertIn("commit_plan", schema["required"])

    def test_minimal_shape_ok(self) -> None:
        role_payload = {key: [] if key.endswith("s") else "" for key in role_analysis_schema()["required"]}
        role_payload["confidence"] = 0.5
        role_payload["top_problems"] = []
        role_payload["candidate_paths"] = []
        role_payload["recommended_steps"] = []
        role_payload["tests"] = []
        role_payload["risks"] = []
        role_payload["edits"] = []
        role_payload["assumptions"] = []
        role_payload["questions"] = []
        role_payload["stop_conditions"] = []
        self.assertTrue(minimal_shape_ok(role_payload, synthesis=False))


if __name__ == "__main__":
    unittest.main()
