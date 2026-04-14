from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moredakka.doctor import run_doctor
from moredakka.util import run_command


class DoctorRepoChecksTests(unittest.TestCase):
    def test_doctor_warns_when_not_in_git_repo(self) -> None:
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
        self.assertEqual(checks["repo"].status, "warn")
        self.assertEqual(checks["base_ref"].status, "warn")

    def test_doctor_fails_when_configured_base_ref_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "moredakka.toml").write_text("[defaults]\nbase_ref = 'does-not-exist'\n", encoding="utf-8")
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            run_command(["git", "init"], cwd=root, check=True)
            run_command(["git", "branch", "-m", "main"], cwd=root, check=True)
            run_command(["git", "add", "."], cwd=root, check=True)
            run_command(
                [
                    "git",
                    "-c",
                    "user.name=Test User",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "-m",
                    "init",
                ],
                cwd=root,
                check=True,
            )

            report = run_doctor(
                cwd=root,
                env={"OPENROUTER_API_KEY": "test-key"},
                version_info=(3, 11, 9),
                which=lambda name: f"/usr/bin/{name}",
                module_available=lambda name: name == "openai",
            )

        checks = {check.name: check for check in report.checks}
        self.assertEqual(checks["repo"].status, "pass")
        self.assertEqual(checks["base_ref"].status, "fail")
        self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
