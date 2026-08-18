"""Tests for the fix-report builders."""

import unittest

from rdc_harness import build_fix_report, render_markdown


class TestBuildFixReport(unittest.TestCase):
    def test_ok_report(self):
        result = {
            "status": "ok",
            "round": 1,
            "source": "fixed_source",
            "history": [
                {"round": 0, "score": 0.5},
                {"round": 1, "score": 0.01},
            ],
        }
        rep = build_fix_report(result=result, original_hlsl="orig",
                               target_event_id=7, stage="pixel")
        self.assertEqual(rep["status"], "ok")
        self.assertEqual(rep["rounds"], 2)
        self.assertEqual(rep["best_score"], 0.01)
        self.assertEqual(rep["final_source"], "fixed_source")
        self.assertEqual(rep["target"], {"event_id": 7, "stage": "pixel"})

    def test_exhausted_uses_last_source(self):
        result = {"status": "exhausted", "last_source": "last", "history": []}
        rep = build_fix_report(result=result, original_hlsl="orig")
        self.assertEqual(rep["final_source"], "last")

    def test_needs_rebuild_carries_l1(self):
        result = {"status": "needs_rebuild", "l1": {"summary": {"fail": 1}}}
        rep = build_fix_report(result=result, original_hlsl="orig")
        self.assertEqual(rep["status"], "needs_rebuild")
        self.assertIn("l1_blocking", rep)

    def test_empty_history_best_score_defaults_to_one(self):
        result = {"status": "exhausted", "last_source": "x", "history": []}
        rep = build_fix_report(result=result, original_hlsl="orig")
        self.assertEqual(rep["best_score"], 1.0)


class TestRenderMarkdown(unittest.TestCase):
    def test_renders_status_and_header(self):
        rep = build_fix_report(
            result={"status": "ok", "history": [
                {"round": 0, "score": 0.0, "l2": {"summary": {}, "checks": []}},
            ]},
            original_hlsl="orig", target_event_id=7, stage="pixel",
        )
        md = render_markdown(rep, "orig")
        self.assertIn("RenderDoc Shader Fix Report", md)
        self.assertIn("ok", md)

    def test_empty_report_has_footer(self):
        rep = build_fix_report(
            result={"status": "ok", "history": []},
            original_hlsl="orig",
        )
        md = render_markdown(rep, "orig")
        self.assertIn("No rounds captured", md)

    def test_diff_included_when_source_changed(self):
        rep = build_fix_report(
            result={"status": "ok", "source": "orig\n+fixed\n",
                    "history": [{"round": 0, "score": 0.0}]},
            original_hlsl="orig\n",
        )
        md = render_markdown(rep, "orig\n")
        self.assertIn("Final shader patch", md)
        self.assertIn("+fixed", md)


if __name__ == "__main__":
    unittest.main()
