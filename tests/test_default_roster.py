from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moredakka.config import load_config
from moredakka.doctor import run_doctor


class DefaultRosterTests(unittest.TestCase):
    def test_default_config_uses_diverse_openrouter_role_roster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(cwd=Path(tmp))

        role_to_provider = {name: role.provider for name, role in config.roles.items()}
        provider_to_model = {name: provider.model for name, provider in config.providers.items()}

        self.assertEqual(role_to_provider["planner"], "openrouter_planner")
        self.assertEqual(role_to_provider["implementer"], "openrouter_implementer")
        self.assertEqual(role_to_provider["breaker"], "openrouter_breaker")
        self.assertEqual(role_to_provider["minimalist"], "openrouter_minimalist")
        self.assertEqual(role_to_provider["synthesizer"], "openrouter_synthesizer")
        self.assertEqual(provider_to_model["openrouter_planner"], "anthropic/claude-opus-4.6")
        self.assertEqual(provider_to_model["openrouter_implementer"], "openai/gpt-5.4")
        self.assertEqual(provider_to_model["openrouter_breaker"], "google/gemini-3.1-pro-preview")
        self.assertEqual(provider_to_model["openrouter_minimalist"], "openai/gpt-5.4-mini")
        self.assertEqual(provider_to_model["openrouter_synthesizer"], "openai/gpt-5.4")

    def test_doctor_reports_pass_for_default_openrouter_roster_with_one_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = run_doctor(
                cwd=root,
                env={"OPENROUTER_API_KEY": "test-key"},
                version_info=(3, 11, 9),
                which=lambda name: f"/usr/bin/{name}",
                module_available=lambda name: name == "openai",
            )

        checks = {check.name: check for check in report.checks}
        self.assertTrue(report.ok)
        self.assertEqual(checks["provider:openrouter_planner"].status, "pass")
        self.assertEqual(checks["provider:openrouter_breaker"].status, "pass")
        self.assertEqual(checks["roster_diversity"].status, "pass")


if __name__ == "__main__":
    unittest.main()
