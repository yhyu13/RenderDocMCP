"""Tests for the L1 deterministic rule engine + auto-red-flags."""

import unittest

from rdc_harness import (
    CheckStatus,
    Thresholds,
    detect_red_flags,
    run_deterministic,
)


def healthy_frame():
    """A frame that should pass every rule."""
    return {
        "total_gpu_ms": 12.0,
        "fps_target_ms": 16.67,
        "api_stats": {"draw_calls": 1500, "state_changes": 50, "rt_switches": 10},
        "gpu_stage_breakdown_ms": {
            "vertex_shader": 2.0, "pixel_shader": 3.0, "output_merger": 2.0,
        },
        "memory_bandwidth": {"l2_throughput_pct": 50.0, "bandwidth_status": "healthy"},
        "top_passes_by_ms": [
            {"name": "Lighting", "ms": 3.0, "draws": 300},
            {"name": "UI", "ms": 1.0, "draws": 50},
        ],
        "top_resources": {"textures": [
            {"name": "t0", "width": 1024, "height": 1024, "format": "BC7", "mip_levels": 8},
        ]},
        "batching_issues": {"same_mesh_different_pso": 3},
        "overdraw_estimate": 3.0,
    }


class TestFrameRules(unittest.TestCase):
    def test_healthy_frame_all_pass(self):
        report = run_deterministic(healthy_frame())
        self.assertTrue(report.all_pass(), report.to_dict())

    def test_fps_budget_fail(self):
        frame = healthy_frame()
        frame["total_gpu_ms"] = 20.0
        report = run_deterministic(frame)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["fps_budget"], CheckStatus.FAIL)

    def test_pixel_bound_bottleneck(self):
        frame = healthy_frame()
        frame["gpu_stage_breakdown_ms"] = {
            "vertex_shader": 1.0, "pixel_shader": 9.0, "output_merger": 1.0,
        }
        report = run_deterministic(frame)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["bottleneck"], CheckStatus.FAIL)

    def test_draw_count_fail(self):
        frame = healthy_frame()
        frame["api_stats"]["draw_calls"] = 4000
        report = run_deterministic(frame)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["draw_count"], CheckStatus.FAIL)

    def test_oversized_texture(self):
        frame = healthy_frame()
        frame["top_resources"]["textures"] = [
            {"name": "big", "width": 8192, "height": 8192, "format": "BC7", "mip_levels": 8},
        ]
        report = run_deterministic(frame)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["oversized_texture"], CheckStatus.FAIL)

    def test_uncompressed_and_unmipped(self):
        frame = healthy_frame()
        frame["top_resources"]["textures"] = [
            {"name": "raw", "width": 1024, "height": 1024, "format": "RGBA8", "mip_levels": 1},
        ]
        report = run_deterministic(frame)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["uncompressed_texture"], CheckStatus.FAIL)
        self.assertEqual(rules["unmipped_texture"], CheckStatus.FAIL)

    def test_setpass_and_rt_switch(self):
        frame = healthy_frame()
        frame["api_stats"]["state_changes"] = 500
        frame["api_stats"]["rt_switches"] = 120
        report = run_deterministic(frame)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["setpass_burst"], CheckStatus.FAIL)
        self.assertEqual(rules["rt_switching"], CheckStatus.FAIL)


class TestRedFlags(unittest.TestCase):
    def test_red_flags_only_failures(self):
        frame = healthy_frame()
        frame["total_gpu_ms"] = 30.0
        frame["api_stats"]["draw_calls"] = 9000
        flags = detect_red_flags(frame)
        rules = {f.rule for f in flags}
        self.assertIn("fps_budget", rules)
        self.assertIn("draw_count", rules)
        self.assertNotIn("bottleneck", rules)  # not failing -> not a red flag

    def test_no_red_flags_on_healthy(self):
        self.assertEqual(detect_red_flags(healthy_frame()), [])


class TestPassRules(unittest.TestCase):
    def test_min_lod_constraint(self):
        frame = healthy_frame()
        passes = [{
            "samplers": [{"slot": 0, "name": "s", "min_lod": 5, "mip_levels": 3}],
        }]
        report = run_deterministic(frame, passes=passes)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["min_lod"], CheckStatus.FAIL)

    def test_binding_completeness(self):
        pipeline = {"shaders": {"pixel": {"resources": []}}}
        report = run_deterministic(healthy_frame(), pipeline=pipeline)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["binding_completeness"], CheckStatus.FAIL)


class TestThresholds(unittest.TestCase):
    def test_with_overrides(self):
        t = Thresholds().with_overrides(draw_call_count=10)
        self.assertEqual(t.draw_call_count, 10)
        self.assertEqual(t.ps_ratio_pct, 50.0)


class TestDegradedInputs(unittest.TestCase):
    """Missing data must degrade to SKIP, never a false PASS."""

    def test_missing_bandwidth_emits_skip(self):
        report = run_deterministic({"memory_bandwidth": {}})
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules.get("bandwidth"), CheckStatus.SKIP)

    def test_missing_mapping_emits_skip(self):
        report = run_deterministic({"total_gpu_ms": 10.0})
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules.get("bandwidth"), CheckStatus.SKIP)

    def test_empty_frame_does_not_vacuously_pass(self):
        report = run_deterministic({})
        self.assertFalse(report.all_pass())
        self.assertGreater(len(report.checks), 0)

    def test_oversized_integer_does_not_crash(self):
        frame = {"total_gpu_ms": 10 ** 400, "fps_target_ms": 16.67}
        report = run_deterministic(frame)  # must not raise
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules.get("fps_budget"), CheckStatus.SKIP)

    def test_min_lod_empty_list_no_false_pass(self):
        report = run_deterministic(healthy_frame(), passes=[{"samplers": []}])
        rules = {c.rule for c in report.checks}
        self.assertNotIn("min_lod", rules)

    def test_min_lod_valid_emits_pass(self):
        passes = [{"samplers": [{"slot": 0, "name": "s", "min_lod": 0, "mip_levels": 8}]}]
        report = run_deterministic(healthy_frame(), passes=passes)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules.get("min_lod"), CheckStatus.PASS)


if __name__ == "__main__":
    unittest.main()
