"""Tests for structured models (VerificationReport)."""

import unittest

from rdc_harness import (
    CheckResult,
    CheckStatus,
    Severity,
    VerificationReport,
)


class TestVerificationReport(unittest.TestCase):
    def test_all_pass_true_when_no_fail(self):
        report = VerificationReport("L1", [
            CheckResult("a", CheckStatus.PASS, Severity.LOW, "ok"),
            CheckResult("b", CheckStatus.WARN, Severity.MEDIUM, "meh"),
            CheckResult("c", CheckStatus.SKIP, Severity.LOW, "no data"),
        ])
        self.assertTrue(report.all_pass())

    def test_all_pass_false_on_fail(self):
        report = VerificationReport("L1", [
            CheckResult("a", CheckStatus.FAIL, Severity.HIGH, "bad"),
        ])
        self.assertFalse(report.all_pass())

    def test_all_pass_false_when_empty(self):
        self.assertFalse(VerificationReport("L1", []).all_pass())

    def test_all_pass_false_when_only_skip(self):
        report = VerificationReport("L1", [
            CheckResult("a", CheckStatus.SKIP, Severity.LOW, "no data"),
        ])
        self.assertFalse(report.all_pass())

    def test_summary_counts(self):
        report = VerificationReport("L1", [
            CheckResult("a", CheckStatus.PASS, Severity.LOW, ""),
            CheckResult("b", CheckStatus.PASS, Severity.LOW, ""),
            CheckResult("c", CheckStatus.FAIL, Severity.HIGH, ""),
            CheckResult("d", CheckStatus.WARN, Severity.MEDIUM, ""),
        ])
        self.assertEqual(report.summary, {
            "pass": 2, "fail": 1, "warn": 1, "skip": 0, "total": 4,
        })

    def test_to_dict_serializable(self):
        report = VerificationReport("L2", [
            CheckResult("rt_hash", CheckStatus.FAIL, Severity.HIGH, "mismatch",
                        expected="abc", actual="def", evidence={"x": 1}),
        ])
        d = report.to_dict()
        self.assertEqual(d["layer"], "L2")
        self.assertEqual(d["checks"][0]["rule"], "rt_hash")
        self.assertEqual(d["checks"][0]["expected"], "abc")


if __name__ == "__main__":
    unittest.main()
