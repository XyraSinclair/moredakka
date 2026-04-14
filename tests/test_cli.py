from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from moredakka.cli import main


class CliTests(unittest.TestCase):
    def test_review_with_missing_base_ref_exits_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            previous_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                from moredakka.util import run_command

                run_command(["git", "init"], cwd=root, check=True)
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

                stdout_buffer = io.StringIO()
                stderr_buffer = io.StringIO()
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    exit_code = main(["review", "--base-ref", "does-not-exist"])
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout_buffer.getvalue(), "")
        self.assertIn("error:", stderr_buffer.getvalue())
        self.assertIn("does-not-exist", stderr_buffer.getvalue())
        self.assertNotIn("Traceback", stderr_buffer.getvalue())

    @patch("moredakka.cli.run_doctor")
    @patch("moredakka.cli.render_doctor_markdown", return_value="# doctor\n")
    def test_doctor_returns_nonzero_on_blocking_failures(
        self,
        _mock_render: SimpleNamespace,
        mock_run_doctor: SimpleNamespace,
    ) -> None:
        mock_run_doctor.return_value = SimpleNamespace(ok=False)

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(["doctor"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(buffer.getvalue(), "# doctor\n")

    def test_pack_emits_json_from_fresh_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")

            buffer = io.StringIO()
            previous_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                with redirect_stdout(buffer):
                    exit_code = main(["pack", "--mode", "plan", "--char-budget", "1200"])
            finally:
                os.chdir(previous_cwd)

            payload = json.loads(buffer.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertIn("context_packet", payload)
            self.assertEqual(payload["context_packet"]["mode"], "plan")

    @patch("moredakka.cli.render_json", return_value='{"ok": true}\n')
    @patch("moredakka.cli.render_markdown", return_value="# report\n")
    @patch("moredakka.cli.run_workflow")
    def test_here_defaults_to_one_round(
        self,
        mock_run_workflow: SimpleNamespace,
        _mock_render_markdown: SimpleNamespace,
        _mock_render_json: SimpleNamespace,
    ) -> None:
        mock_run_workflow.return_value = SimpleNamespace(
            packet=SimpleNamespace(),
            synthesis={},
            rounds=[],
            provider_notes=[],
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")

            buffer = io.StringIO()
            previous_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                with redirect_stdout(buffer):
                    exit_code = main(["here"])
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_run_workflow.call_args.kwargs["rounds"], 1)


if __name__ == "__main__":
    unittest.main()
