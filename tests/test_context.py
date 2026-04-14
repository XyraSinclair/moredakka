from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moredakka.context import build_context_packet, render_context_packet
from moredakka.util import run_command


class ContextTests(unittest.TestCase):
    def test_context_packet_without_git_still_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Demo\n\nSome context.", encoding="utf-8")
            (root / "main.py").write_text("print('hi')\n", encoding="utf-8")

            packet = build_context_packet(
                cwd=root,
                mode="plan",
                objective=None,
                base_ref="main",
                char_budget=4000,
            )
            rendered = render_context_packet(packet, char_budget=4000)

            self.assertIn("inferred_objective", rendered)
            self.assertIn("repo_root", rendered)
            self.assertIn("README.md", rendered)

    def test_context_packet_preserves_hidden_file_paths_in_git_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidden_file = root / ".agents" / "skills" / "moredakka" / "SKILL.md"
            hidden_file.parent.mkdir(parents=True)
            hidden_file.write_text("initial\n", encoding="utf-8")

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

            hidden_file.write_text("changed\n", encoding="utf-8")

            packet = build_context_packet(
                cwd=root,
                mode="plan",
                objective=None,
                base_ref="main",
                char_budget=4000,
            )

            self.assertEqual(packet.status_summary[0], "M .agents/skills/moredakka/SKILL.md")
            self.assertEqual(packet.changed_files[0], ".agents/skills/moredakka/SKILL.md")

    def test_context_packet_expands_untracked_directories_into_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src" / "pkg"
            src.mkdir(parents=True)
            (src / "a.py").write_text("print('a')\n", encoding="utf-8")
            (src / "b.py").write_text("print('b')\n", encoding="utf-8")

            run_command(["git", "init"], cwd=root, check=True)

            packet = build_context_packet(
                cwd=root,
                mode="plan",
                objective=None,
                base_ref="main",
                char_budget=4000,
            )

            self.assertIn("?? src/", packet.status_summary)
            self.assertEqual(packet.changed_files[:2], ["src/pkg/a.py", "src/pkg/b.py"])
            self.assertEqual([item.path for item in packet.file_excerpts], ["src/pkg/a.py", "src/pkg/b.py"])

    def test_review_mode_uses_branch_diff_files_for_changed_files_and_excerpts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            run_command(["git", "checkout", "-b", "feature/test-review"], cwd=root, check=True)
            (root / "service.py").write_text("print('feature change')\n", encoding="utf-8")
            run_command(["git", "add", "service.py"], cwd=root, check=True)
            run_command(
                [
                    "git",
                    "-c",
                    "user.name=Test User",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "-m",
                    "add service",
                ],
                cwd=root,
                check=True,
            )

            packet = build_context_packet(
                cwd=root,
                mode="review",
                objective=None,
                base_ref="main",
                char_budget=4000,
            )

            self.assertIn("service.py", packet.changed_files)
            self.assertEqual([item.path for item in packet.file_excerpts], ["service.py"])

    def test_review_mode_rejects_missing_base_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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

            with self.assertRaises(RuntimeError):
                build_context_packet(
                    cwd=root,
                    mode="review",
                    objective=None,
                    base_ref="does-not-exist",
                    char_budget=4000,
                )


if __name__ == "__main__":
    unittest.main()
