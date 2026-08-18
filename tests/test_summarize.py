"""Tests for Layer1/Layer2 summary builders + token compaction."""

import unittest

from rdc_harness import (
    build_frame_summary,
    build_pass_summary,
    compact_frame,
    estimate_tokens,
)


class TestFrameSummary(unittest.TestCase):
    def test_build_adds_auto_red_flags(self):
        frame = build_frame_summary(
            total_gpu_ms=30.0,
            fps_target_ms=16.67,
            api_stats={"draw_calls": 9000},
        )
        self.assertIn("auto_red_flags", frame)
        rules = {f["rule"] for f in frame["auto_red_flags"]}
        self.assertIn("fps_budget", rules)
        self.assertIn("draw_count", rules)

    def test_build_healthy_has_no_flags(self):
        frame = build_frame_summary(
            total_gpu_ms=12.0,
            fps_target_ms=16.67,
            api_stats={"draw_calls": 100},
            gpu_stage_breakdown_ms={"vertex_shader": 1.0, "pixel_shader": 1.0,
                                    "rasterizer": 1.0},
        )
        self.assertEqual(frame["auto_red_flags"], [])


class TestPassSummary(unittest.TestCase):
    def test_build_pass_summary(self):
        ps = build_pass_summary(
            name="Lighting",
            total_ms=6.2,
            draw_count=412,
            stage_breakdown_ms={"vs": 0.8, "ps": 4.9},
            batching_issues={"same_mesh_different_pso": 47},
            render_targets=["HDRScene"],
        )
        self.assertEqual(ps["pass"], "Lighting")
        self.assertEqual(ps["batching_issues"]["same_mesh_different_pso"], 47)


class TestCompaction(unittest.TestCase):
    def test_compact_includes_flags(self):
        frame = build_frame_summary(
            total_gpu_ms=30.0,
            fps_target_ms=16.67,
            api_stats={"draw_calls": 9000},
            top_passes_by_ms=[{"name": "Lighting", "ms": 6.2, "draws": 412}],
        )
        text = compact_frame(frame)
        self.assertIn("Lighting", text)
        self.assertIn("Frame:", text)

    def test_token_budget_under_200(self):
        frame = build_frame_summary(
            total_gpu_ms=14.0,
            fps_target_ms=16.67,
            api_stats={"draw_calls": 1800},
            top_passes_by_ms=[
                {"name": "Lighting", "ms": 6.2, "draws": 412},
                {"name": "GBuffer", "ms": 2.4, "draws": 847},
            ],
        )
        self.assertLess(estimate_tokens(compact_frame(frame)), 200)


if __name__ == "__main__":
    unittest.main()
