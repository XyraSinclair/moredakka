from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from moredakka.config import ProviderConfig
from moredakka.context import ContextPacket
from moredakka.runlog import (
    accumulate_usage,
    context_rendering_stats,
    estimate_cost_usd,
    latest_run_artifact_summary,
    normalize_usage,
    preflight_run_dir,
    write_run_artifact,
)


class RunlogTests(unittest.TestCase):
    def test_normalize_usage_maps_alias_fields_and_ignores_bool_values(self) -> None:
        usage = {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_token_count": 18,
            "cached_content_token_count": 3,
            "output_tokens_details": {"reasoning_tokens": 2},
            "cost_usd": 0.12,
            "bogus_bool": True,
        }

        normalized = normalize_usage(usage)

        self.assertEqual(normalized["input_tokens"], 11)
        self.assertEqual(normalized["output_tokens"], 7)
        self.assertEqual(normalized["total_tokens"], 18)
        self.assertEqual(normalized["cached_input_tokens"], 3)
        self.assertEqual(normalized["reasoning_tokens"], 2)
        self.assertEqual(normalized["provider_reported_cost_usd"], 0.12)

    def test_estimate_cost_usd_prefers_reported_cost_and_supports_partial_pricing(self) -> None:
        provider = ProviderConfig(
            name="demo",
            kind="openai",
            model="gpt-demo",
            api_key_env="OPENAI_API_KEY",
            input_cost_per_million_tokens=2.0,
            output_cost_per_million_tokens=4.0,
        )
        reported = estimate_cost_usd({"provider_reported_cost_usd": 1.23}, provider)
        partial = estimate_cost_usd({"input_tokens": 500_000}, provider)

        self.assertEqual(reported, 1.23)
        self.assertEqual(partial, 1.0)

    def test_accumulate_usage_sums_present_fields_and_leaves_missing_as_none(self) -> None:
        totals = accumulate_usage(
            [
                {"input_tokens": 10, "output_tokens": 5, "estimated_cost_usd": 0.1},
                {"input_tokens": 3, "reasoning_tokens": 2},
            ]
        )

        self.assertEqual(totals["input_tokens"], 13)
        self.assertEqual(totals["output_tokens"], 5)
        self.assertIsNone(totals["total_tokens"])
        self.assertEqual(totals["reasoning_tokens"], 2)
        self.assertEqual(totals["estimated_cost_usd"], 0.1)

    def test_write_run_artifact_resolves_relative_run_dir_and_partitions_by_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_run_artifact(
                cwd=root,
                run_dir=".moredakka/runs",
                invocation_id="20260414T000000Z-deadbeef",
                artifact={"ok": True},
            )

            self.assertTrue(path.exists())
            self.assertIn("20260414", str(path.parent))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"ok": True})
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_latest_run_artifact_summary_reads_most_recent_valid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = write_run_artifact(
                cwd=root,
                run_dir=".moredakka/runs",
                invocation_id="20260414T000000Z-deadbeef",
                artifact={
                    "invocation": {"run_status": "success", "stop_reason": "max_rounds", "mode": "plan", "directive": None},
                    "query_compilation": {"selected_ops": ["critique"]},
                },
            )
            newer = write_run_artifact(
                cwd=root,
                run_dir=".moredakka/runs",
                invocation_id="20260415T000000Z-feedface",
                artifact={
                    "invocation": {"run_status": "degraded", "stop_reason": "max_total_tokens", "mode": "review", "directive": "continue"},
                    "query_compilation": {"selected_ops": ["branch", "compare"]},
                },
            )
            older.touch()
            newer.touch()

            summary = latest_run_artifact_summary(cwd=root, run_dir=".moredakka/runs")

            self.assertIsNotNone(summary)
            self.assertEqual(summary["run_status"], "degraded")
            self.assertEqual(summary["stop_reason"], "max_total_tokens")
            self.assertEqual(summary["selected_ops"], ["branch", "compare"])
            self.assertEqual(Path(summary["path"]), newer)

    def test_context_rendering_stats_detects_truncation(self) -> None:
        packet = ContextPacket(
            cwd="/tmp/demo",
            repo_root="/tmp/demo",
            mode="plan",
            objective="",
            inferred_objective="objective",
            base_ref="main",
            branch=None,
            changed_files=["a.py", "b.py"],
            diff_excerpt="x" * 40,
        )

        stats = context_rendering_stats(packet, "y" * 20, char_budget=20)

        self.assertEqual(stats["char_budget"], 20)
        self.assertEqual(stats["rendered_chars"], 20)
        self.assertTrue(stats["truncated"])
        self.assertEqual(stats["changed_file_count"], 2)

    def test_preflight_run_dir_creates_and_writes_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved = preflight_run_dir(cwd=root, run_dir=".moredakka/runs")
            self.assertTrue(resolved.exists())
            self.assertFalse((resolved / ".write-probe").exists())


if __name__ == "__main__":
    unittest.main()
