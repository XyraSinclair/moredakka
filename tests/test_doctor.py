from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moredakka.doctor import render_doctor_json, render_doctor_markdown, run_doctor


class DoctorTests(unittest.TestCase):
    def test_run_doctor_flags_old_python_and_missing_active_provider_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = run_doctor(
                cwd=root,
                env={},
                version_info=(3, 9, 6),
                which=lambda name: None,
                module_available=lambda name: False,
            )

        checks = {check.name: check for check in report.checks}
        self.assertFalse(report.ok)
        self.assertEqual(checks["python"].status, "fail")
        self.assertEqual(checks["git"].status, "fail")
        self.assertEqual(checks["provider:openrouter_planner"].status, "fail")
        self.assertEqual(checks["provider:openrouter_breaker"].status, "fail")
        self.assertEqual(checks["roster_diversity"].status, "pass")

    def test_run_doctor_passes_with_valid_runtime_and_active_provider_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = run_doctor(
                cwd=root,
                env={
                    "OPENROUTER_API_KEY": "test-openrouter",
                },
                version_info=(3, 11, 9),
                which=lambda name: f"/usr/bin/{name}",
                module_available=lambda name: name in {"openai"},
            )

        checks = {check.name: check for check in report.checks}
        self.assertTrue(report.ok)
        self.assertEqual(checks["python"].status, "pass")
        self.assertEqual(checks["git"].status, "pass")
        self.assertEqual(checks["config"].status, "pass")
        self.assertEqual(checks["cache_dir"].status, "pass")
        self.assertEqual(checks["provider:openrouter_planner"].status, "pass")
        self.assertEqual(checks["provider:openrouter_implementer"].status, "pass")
        self.assertEqual(checks["provider:openrouter_breaker"].status, "pass")
        self.assertEqual(checks["roster_diversity"].status, "pass")

    def test_renderers_emit_summary_and_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = run_doctor(
                cwd=root,
                env={},
                version_info=(3, 11, 0),
                which=lambda name: f"/usr/bin/{name}",
                module_available=lambda name: True,
            )

        markdown = render_doctor_markdown(report)
        payload = render_doctor_json(report)
        self.assertIn("# moredakka doctor", markdown)
        self.assertIn('"ok":', payload)
        self.assertIn('"checks":', payload)


if __name__ == "__main__":
    unittest.main()
