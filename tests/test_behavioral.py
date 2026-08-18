"""Tests for L2 behavioral verification (pixel diff, hash, PSNR)."""

import unittest

from rdc_harness import (
    CheckStatus,
    pixel_diff,
    psnr,
    rt_hash,
    run_behavioral,
    score_from_report,
    threshold_verdict,
)


def rgba_bytes(r, g, b, a=255, count=16):
    return bytes([r, g, b, a]) * count


class TestPixelDiff(unittest.TestCase):
    def test_identical(self):
        d = pixel_diff(rgba_bytes(10, 20, 30), rgba_bytes(10, 20, 30))
        self.assertEqual(d.changed_pixels, 0)
        self.assertEqual(d.changed_fraction, 0.0)
        self.assertEqual(d.mean_abs_error, 0.0)

    def test_fully_different(self):
        d = pixel_diff(rgba_bytes(0, 0, 0), rgba_bytes(255, 255, 255))
        self.assertEqual(d.changed_fraction, 1.0)
        self.assertEqual(d.max_abs_error, 255)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            pixel_diff(rgba_bytes(0, 0, 0, count=4), rgba_bytes(0, 0, 0, count=8))


class TestHashAndPsnr(unittest.TestCase):
    def test_rt_hash_deterministic(self):
        data = rgba_bytes(1, 2, 3)
        self.assertEqual(rt_hash(data), rt_hash(data))
        self.assertEqual(len(rt_hash(data)), 64)

    def test_rt_hash_accepts_memoryview(self):
        data = bytearray(rgba_bytes(1, 2, 3))
        self.assertEqual(rt_hash(data), rt_hash(memoryview(data)))

    def test_psnr_identical_is_inf(self):
        self.assertEqual(psnr(rgba_bytes(5, 5, 5), rgba_bytes(5, 5, 5)), float("inf"))

    def test_psnr_finite_when_different(self):
        p = psnr(rgba_bytes(0, 0, 0), rgba_bytes(255, 255, 255))
        self.assertLess(p, 30.0)


class TestRunBehavioral(unittest.TestCase):
    def test_perfect_match_passes(self):
        data = rgba_bytes(10, 20, 30)
        report = run_behavioral(data, data, expected_hash=rt_hash(data))
        self.assertTrue(report.all_pass(), report.to_dict())

    def test_hash_mismatch_fails(self):
        actual = rgba_bytes(10, 20, 30)
        golden = rgba_bytes(10, 20, 30)
        report = run_behavioral(actual, golden, expected_hash="0" * 64)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["rt_hash"], CheckStatus.FAIL)
        self.assertEqual(score_from_report(report), 1.0)

    def test_hash_mismatch_short_circuits_pixel_work(self):
        actual = rgba_bytes(10, 20, 30)
        golden = rgba_bytes(10, 20, 30)
        report = run_behavioral(actual, golden, expected_hash="0" * 64)
        rules = {c.rule for c in report.checks}
        self.assertIn("rt_hash", rules)
        self.assertNotIn("pixel_diff", rules)
        self.assertNotIn("psnr", rules)

    def test_pixel_diff_warn_then_fail_thresholds(self):
        golden = rgba_bytes(0, 0, 0, count=100)
        # 2 of 100 pixels changed = 2% -> warn (between 1% and 5%)
        actual = bytearray(golden)
        actual[0:4] = b"\xff\xff\xff\xff"
        actual[4:8] = b"\xff\xff\xff\xff"
        report = run_behavioral(bytes(actual), golden)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["pixel_diff"], CheckStatus.WARN)

        # 10 of 100 changed = 10% -> fail
        for i in range(10):
            actual[i * 4:i * 4 + 4] = b"\xff\xff\xff\xff"
        report = run_behavioral(bytes(actual), golden)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["pixel_diff"], CheckStatus.FAIL)

    def test_pixel_history_overdraw(self):
        data = rgba_bytes(0, 0, 0)
        report = run_behavioral(data, data, pixel_history_draw_count=20)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules["pixel_history_overdraw"], CheckStatus.WARN)


class TestScoreAndVerdict(unittest.TestCase):
    def test_score_perfect_is_zero(self):
        data = rgba_bytes(1, 2, 3)
        report = run_behavioral(data, data)
        self.assertEqual(score_from_report(report), 0.0)

    def test_score_unknown_returns_one(self):
        # An L2 report with no pixel-diff / rt_hash signal must not be treated
        # as "converged" — unknown quality => worst-case badness.
        from rdc_harness import CheckResult, CheckStatus, Severity, VerificationReport
        empty = VerificationReport("L2", [
            CheckResult("other", CheckStatus.PASS, Severity.LOW, "no signal"),
        ])
        self.assertEqual(score_from_report(empty), 1.0)

    def test_threshold_verdict(self):
        data = rgba_bytes(1, 2, 3)
        self.assertEqual(threshold_verdict(run_behavioral(data, data)), "ok")

    def test_threshold_verdict_fail_on_psnr(self):
        # 2% changed pixels -> pixel_diff WARN; PSNR far below floor -> MEDIUM
        # FAIL. verdict must be "fail" (status-based), not "warn".
        golden = rgba_bytes(0, 0, 0, count=100)
        actual = bytearray(golden)
        actual[0:4] = b"\xff\xff\xff\xff"
        actual[4:8] = b"\xff\xff\xff\xff"
        report = run_behavioral(bytes(actual), golden)
        self.assertEqual(threshold_verdict(report), "fail")


class TestNumpyParity(unittest.TestCase):
    def test_numpy_matches_pure_python(self):
        import rdc_harness.behavioral as bh

        actual = bytes([i % 256 for i in range(400)])  # 100 RGBA pixels
        golden = bytes([(i * 3) % 256 for i in range(400)])

        fast = bh.pixel_diff(actual, golden)
        fast_psnr = bh.psnr(actual, golden)

        saved = bh._np
        bh._np = None
        try:
            slow = bh.pixel_diff(actual, golden)
            slow_psnr = bh.psnr(actual, golden)
        finally:
            bh._np = saved

        self.assertEqual(fast.total_pixels, slow.total_pixels)
        self.assertEqual(fast.changed_pixels, slow.changed_pixels)
        self.assertAlmostEqual(fast.mean_abs_error, slow.mean_abs_error, places=6)
        self.assertEqual(fast.max_abs_error, slow.max_abs_error)
        self.assertAlmostEqual(fast_psnr, slow_psnr, places=6)


if __name__ == "__main__":
    unittest.main()
