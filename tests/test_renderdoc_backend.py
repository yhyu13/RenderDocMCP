"""Tests for the bridge-driven RenderDocShaderBackend adapter."""

import base64
import unittest

from rdc_harness import RenderDocShaderBackend, ShaderCompileError


class FakeBridge:
    """In-memory stand-in for the MCP bridge client."""

    def __init__(self, calls=None):
        self.calls = []
        self.responses = dict(calls or {})

    def call(self, method, params=None):
        params = params or {}
        self.calls.append((method, params))
        return self.responses.get(method)


def _texture_result(pixel_bytes, fmt="R8G8B8A8_UNORM"):
    return {
        "content_base64": base64.b64encode(pixel_bytes).decode("ascii"),
        "format": fmt,
    }


class TestRenderDocShaderBackend(unittest.TestCase):
    def _backend(self, **kwargs):
        return RenderDocShaderBackend(
            bridge=FakeBridge({
                "get_shader_source": {"entry_point": "PSMain"},
                "compile_shader": {"resource_id": "ResourceId::999", "messages": ""},
                "replace_shader": {"original_resource_id": "ResourceId::1"},
                "replay_event": {"replayed": True},
            }),
            event_id=42,
            **kwargs
        )

    def test_compile_shader_uses_entry_point(self):
        backend = self._backend()
        handle = backend.compile_shader("float4 main() { return 0; }", "pixel")
        self.assertEqual(handle, "ResourceId::999")
        # entry point discovered from the capture when not provided.
        compile_call = [c for c in backend._bridge.calls if c[0] == "compile_shader"]
        self.assertEqual(compile_call[0][1]["entry"], "PSMain")

    def test_compile_shader_uses_explicit_entry(self):
        backend = self._backend(entry="CustomPS")
        backend.compile_shader("float4 main() { return 0; }", "pixel")
        compile_call = [c for c in backend._bridge.calls if c[0] == "compile_shader"]
        self.assertEqual(compile_call[0][1]["entry"], "CustomPS")
        # explicit entry must not trigger a get_shader_source round-trip.
        self.assertFalse(
            any(c[0] == "get_shader_source" for c in backend._bridge.calls)
        )

    def test_compile_shader_raises_on_null_resource(self):
        bridge = FakeBridge({
            "get_shader_source": {"entry_point": "PSMain"},
            "compile_shader": {"resource_id": "", "messages": "syntax error"},
        })
        backend = RenderDocShaderBackend(bridge=bridge, event_id=42)
        with self.assertRaises(ShaderCompileError):
            backend.compile_shader("bad", "pixel")

    def test_inject_and_replay_call_bridge(self):
        backend = self._backend()
        backend.inject_shader(42, "pixel", "ResourceId::999")
        backend.replay(42)
        methods = [c[0] for c in backend._bridge.calls]
        self.assertIn("replace_shader", methods)
        self.assertIn("replay_event", methods)

    def test_run_l1_returns_report(self):
        bridge = FakeBridge({
            "get_frame_summary": {"statistics": {"draw_calls": 10}},
            "get_pipeline_state": {"shaders": {"pixel": {"resources": [{"slot": 0}]}}},
            "get_debug_messages": {"messages": []},
        })
        backend = RenderDocShaderBackend(bridge=bridge, event_id=42)
        report = backend.run_l1()
        self.assertEqual(report.layer, "L1")
        self.assertTrue(report.checks)  # draw_count + binding_completeness

    def test_run_l1_flags_validation_errors(self):
        bridge = FakeBridge({
            "get_frame_summary": {"statistics": {"draw_calls": 10}},
            "get_pipeline_state": {"shaders": {"pixel": {"resources": [{"slot": 0}]}}},
            "get_debug_messages": {
                "messages": [{"severity": "High", "message": "bad binding"}]
            },
        })
        backend = RenderDocShaderBackend(bridge=bridge, event_id=42)
        report = backend.run_l1()
        validation = [c for c in report.checks if c.rule == "validation_messages"]
        self.assertEqual(len(validation), 1)
        self.assertEqual(validation[0].status.value, "fail")
        self.assertFalse(report.all_pass())

    def test_run_l2_compares_against_golden(self):
        golden = b"\x00\x00\x00\xff" * 4
        bridge = FakeBridge({
            "get_texture_data": _texture_result(golden),
        })
        backend = RenderDocShaderBackend(
            bridge=bridge, event_id=42,
            golden_bytes=golden, render_target="ResourceId::7",
        )
        report = backend.run_l2()
        self.assertEqual(report.layer, "L2")
        # identical buffers -> pixel_diff passes (changed_fraction 0.0).
        self.assertTrue(report.all_pass())

    def test_run_l2_rejects_non_rgba8(self):
        golden = b"\x00\x00\x00\x00" * 4
        bridge = FakeBridge({
            "get_texture_data": _texture_result(golden, fmt="R16G16B16A16_FLOAT"),
        })
        backend = RenderDocShaderBackend(
            bridge=bridge, event_id=42,
            golden_bytes=golden, render_target="ResourceId::7",
        )
        with self.assertRaises(ValueError):
            backend.run_l2()

    def test_run_l2_rejects_size_mismatch(self):
        bridge = FakeBridge({
            "get_texture_data": _texture_result(b"\x00" * 16),
        })
        backend = RenderDocShaderBackend(
            bridge=bridge, event_id=42,
            golden_bytes=b"\x00" * 8, render_target="ResourceId::7",
        )
        with self.assertRaises(ValueError):
            backend.run_l2()

    def test_run_l2_requires_config(self):
        backend = RenderDocShaderBackend(bridge=FakeBridge(), event_id=42)
        with self.assertRaises(ValueError):
            backend.run_l2()

    def test_requires_bridge(self):
        backend = RenderDocShaderBackend(controller=object(), event_id=42)
        with self.assertRaises(RuntimeError):
            backend.compile_shader("float4 main() { return 0; }", "pixel")


if __name__ == "__main__":
    unittest.main()
