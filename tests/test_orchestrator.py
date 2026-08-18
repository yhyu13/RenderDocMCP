"""Tests for the shader-edit/replay/verify orchestrator loop."""

import unittest

from rdc_harness import (
    CheckResult,
    CheckStatus,
    Severity,
    ShaderCompileError,
    VerificationReport,
    iterate_shader_fix,
)


def _l1_pass():
    return VerificationReport("L1", [
        CheckResult("x", CheckStatus.PASS, Severity.LOW, "ok"),
    ])


def _l1_fail():
    return VerificationReport("L1", [
        CheckResult("binding", CheckStatus.FAIL, Severity.HIGH, "no binding"),
    ])


def _l2(score):
    status = CheckStatus.PASS if score <= 0.05 else CheckStatus.FAIL
    return VerificationReport("L2", [
        CheckResult("pixel_diff", status, Severity.MEDIUM, f"frac {score}",
                    evidence={"changed_fraction": score}),
    ])


class FakeBackend:
    """Deterministic in-memory backend for the loop."""

    def __init__(self, scores, l1_fail=False, fail_compile=False):
        self.scores = list(scores)
        self.l1_fail = l1_fail
        self.fail_compile = fail_compile
        self.calls = 0
        self.injected = []
        self.replayed = []

    def compile_shader(self, hlsl, stage):
        if self.fail_compile or hlsl == "BAD_SOURCE":
            raise ShaderCompileError("compile failed")
        return "shader:" + hlsl

    def inject_shader(self, event_id, stage, bytecode):
        self.injected.append((event_id, stage))

    def replay(self, event_id):
        self.replayed.append(event_id)

    def run_l1(self):
        return _l1_fail() if self.l1_fail else _l1_pass()

    def run_l2(self):
        score = self.scores[min(self.calls, len(self.scores) - 1)]
        self.calls += 1
        return _l2(score)


class FakePatcher:
    """Records history and returns a deterministic next source."""

    def __init__(self):
        self.calls = []

    def patch(self, original, feedback, history):
        self.calls.append((original, feedback, list(history)))
        return f"patched_{len(self.calls)}"


class TestOrchestrator(unittest.TestCase):
    def test_converges_to_ok(self):
        backend = FakeBackend(scores=[0.5, 0.2, 0.01])
        patcher = FakePatcher()
        result = iterate_shader_fix(
            original_hlsl="orig", backend=backend, patcher=patcher,
            event_id=42, stage="pixel", max_round=5, pass_threshold=0.05,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["round"], 2)
        self.assertEqual(len(result["history"]), 3)
        # The returned source is the final patched source (doc3 §4.2 returns
        # "source": current_hlsl), while the patcher always receives the original.
        self.assertEqual(result["source"], "patched_2")
        self.assertEqual(len(patcher.calls), 2)  # patched on rounds 0 and 1 only
        self.assertEqual(patcher.calls[0][0], "orig")
        self.assertEqual(patcher.calls[1][0], "orig")

    def test_static_fail(self):
        backend = FakeBackend(scores=[0.5], fail_compile=True)
        result = iterate_shader_fix(
            original_hlsl="orig", backend=backend, patcher=FakePatcher(),
            event_id=42, stage="pixel", max_round=3,
        )
        self.assertEqual(result["status"], "static_fail")
        self.assertEqual(result["round"], 0)

    def test_needs_rebuild_when_l1_fails(self):
        backend = FakeBackend(scores=[0.5], l1_fail=True)
        result = iterate_shader_fix(
            original_hlsl="orig", backend=backend, patcher=FakePatcher(),
            event_id=42, stage="pixel", max_round=3,
        )
        self.assertEqual(result["status"], "needs_rebuild")
        self.assertIn("l1", result)

    def test_exhausted_when_never_converges(self):
        backend = FakeBackend(scores=[0.5, 0.5, 0.5])
        patcher = FakePatcher()
        result = iterate_shader_fix(
            original_hlsl="orig", backend=backend, patcher=patcher,
            event_id=42, stage="pixel", max_round=3, pass_threshold=0.05,
        )
        self.assertEqual(result["status"], "exhausted")
        self.assertEqual(len(patcher.calls), 3)

    def test_l1_runs_before_l2(self):
        # With l1 failing, run_l2 must never be called (ordering guarantee).
        backend = FakeBackend(scores=[0.5], l1_fail=True)
        iterate_shader_fix(
            original_hlsl="orig", backend=backend, patcher=FakePatcher(),
            event_id=42, stage="pixel", max_round=3,
        )
        self.assertEqual(backend.calls, 0)

    def test_max_round_zero_returns_exhausted(self):
        backend = FakeBackend(scores=[0.5])
        result = iterate_shader_fix(
            original_hlsl="orig", backend=backend, patcher=FakePatcher(),
            event_id=42, stage="pixel", max_round=0,
        )
        self.assertEqual(result["status"], "exhausted")
        self.assertEqual(result["history"], [])
        self.assertEqual(backend.calls, 0)

    def test_patch_history_includes_current_round(self):
        backend = FakeBackend(scores=[0.5, 0.5, 0.01])
        patcher = FakePatcher()
        iterate_shader_fix(
            original_hlsl="orig", backend=backend, patcher=patcher,
            event_id=42, stage="pixel", max_round=5, pass_threshold=0.05,
        )
        # patch(round 0) sees [r0]; patch(round 1) sees [r0, r1] — history is
        # cumulative and includes the current round (matches doc3 §4.2).
        self.assertEqual([h["round"] for h in patcher.calls[0][2]], [0])
        self.assertEqual([h["round"] for h in patcher.calls[1][2]], [0, 1])
        for h in patcher.calls[1][2]:
            self.assertIn("score", h)
            self.assertIn("l2", h)

    def test_default_threshold_rejects_warn_band(self):
        # 2% changed = WARN band; with default pass_threshold=0.01 the loop
        # must not report "ok" for a WARN-band regression.
        backend = FakeBackend(scores=[0.02, 0.02, 0.02])
        result = iterate_shader_fix(
            original_hlsl="orig", backend=backend, patcher=FakePatcher(),
            event_id=42, stage="pixel", max_round=3,
        )
        self.assertEqual(result["status"], "exhausted")


if __name__ == "__main__":
    unittest.main()
