from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moredakka.doctor import run_doctor
from moredakka.util import load_local_env


class EnvLoadingTests(unittest.TestCase):
    def test_load_local_env_reads_repo_env_without_overriding_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "src" / "pkg"
            nested.mkdir(parents=True)
            (root / ".env").write_text(
                "OPENROUTER_API_KEY=from-dotenv\nEXTRA_FLAG=yes\n",
                encoding="utf-8",
            )

            loaded = load_local_env(nested, env={"OPENROUTER_API_KEY": "already-set"})

            self.assertEqual(loaded["OPENROUTER_API_KEY"], "already-set")
            self.assertEqual(loaded["EXTRA_FLAG"], "yes")

    def test_run_doctor_uses_repo_env_file_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "OPENROUTER_API_KEY=from-dotenv\n",
                encoding="utf-8",
            )

            report = run_doctor(
                cwd=root,
                version_info=(3, 11, 9),
                which=lambda name: f"/usr/bin/{name}",
                module_available=lambda name: name == "openai",
            )

        checks = {check.name: check for check in report.checks}
        self.assertEqual(checks["provider:openrouter_planner"].status, "pass")
        self.assertEqual(checks["provider:openrouter_breaker"].status, "pass")


if __name__ == "__main__":
    unittest.main()
