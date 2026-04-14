from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moredakka.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_searches_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "src" / "moredakka"
            nested.mkdir(parents=True)
            (root / "moredakka.toml").write_text(
                "[defaults]\nbase_ref = 'develop'\n",
                encoding="utf-8",
            )

            config = load_config(cwd=nested)

            self.assertEqual(config.defaults.base_ref, "develop")

    def test_load_config_rejects_missing_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(RuntimeError):
                load_config(cwd=root, explicit_path=str(root / "missing.toml"))

    def test_load_config_rejects_roles_pointing_to_missing_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text(
                "[roles.breaker]\nprovider = 'missing'\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                load_config(cwd=root)

    def test_load_config_reads_openrouter_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text(
                "\n".join(
                    [
                        "[providers.openrouter]",
                        "kind = 'openrouter'",
                        "model = 'anthropic/claude-sonnet-4.5'",
                        "api_key_env = 'OPENROUTER_API_KEY'",
                        "reasoning_effort = 'high'",
                        "base_url = 'https://openrouter.ai/api/v1'",
                        "app_url = 'https://example.com'",
                        "app_name = 'moredakka-test'",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            config = load_config(cwd=root)

            self.assertEqual(config.providers["openrouter"].kind, "openrouter")
            self.assertEqual(config.providers["openrouter"].app_url, "https://example.com")
            self.assertEqual(config.providers["openrouter"].app_name, "moredakka-test")

    def test_load_config_rejects_invalid_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text(
                "\n".join(
                    [
                        "[defaults]",
                        "mode = 'invalid'",
                        "max_rounds = 0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                load_config(cwd=root)

    def test_load_config_rejects_invalid_novelty_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text(
                "[defaults]\nnovelty_threshold = 1.5\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                load_config(cwd=root)

    def test_load_config_rejects_empty_base_ref_and_provider_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text(
                "\n".join(
                    [
                        "[defaults]",
                        "base_ref = ''",
                        "[providers.openrouter_breaker]",
                        "kind = 'openrouter'",
                        "model = ''",
                        "api_key_env = ''",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                load_config(cwd=root)

    def test_load_config_rejects_invalid_reasoning_effort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text(
                "[providers.openrouter_implementer]\nreasoning_effort = 'extreme'\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                load_config(cwd=root)

    def test_load_config_reads_run_and_pricing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text(
                "\n".join(
                    [
                        "[defaults]",
                        "run_dir = '.moredakka/runs'",
                        "max_total_tokens = 12345",
                        "max_cost_usd = 1.25",
                        "max_wall_seconds = 30",
                        "[providers.openrouter_planner]",
                        "input_cost_per_million_tokens = 2.5",
                        "output_cost_per_million_tokens = 10.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            config = load_config(cwd=root)

            self.assertEqual(config.defaults.run_dir, '.moredakka/runs')
            self.assertEqual(config.defaults.max_total_tokens, 12345)
            self.assertEqual(config.defaults.max_cost_usd, 1.25)
            self.assertEqual(config.defaults.max_wall_seconds, 30)
            self.assertEqual(config.providers['openrouter_planner'].input_cost_per_million_tokens, 2.5)
            self.assertEqual(config.providers['openrouter_planner'].output_cost_per_million_tokens, 10.0)

    def test_load_config_rejects_invalid_budget_and_pricing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text(
                "\n".join(
                    [
                        "[defaults]",
                        "max_total_tokens = 0",
                        "[providers.openrouter_planner]",
                        "input_cost_per_million_tokens = -1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                load_config(cwd=root)


if __name__ == "__main__":
    unittest.main()
