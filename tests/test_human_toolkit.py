"""GPU-free tests for the human 90% toolkit helpers + invisible-draw rules."""

import struct
import unittest

from rdc_harness import (
    CheckStatus,
    UNITY_EXCLUDE_MARKERS,
    cap_history,
    check_invisible_pipeline,
    decode_position_vertices,
    resolve_draw_filters,
    run_deterministic,
    serialize_pixel_modification,
)
from rdc_harness.human_toolkit import ndc_xy


class TestResolveDrawFilters(unittest.TestCase):
    def test_no_preset_passthrough(self):
        mf, ex = resolve_draw_filters(None, "Shadows", ["UI"])
        self.assertEqual(mf, "Shadows")
        self.assertEqual(ex, ["UI"])

    def test_unity_preset_defaults(self):
        mf, ex = resolve_draw_filters("unity_game_rendering")
        self.assertEqual(mf, "Camera.Render")
        self.assertEqual(ex, list(UNITY_EXCLUDE_MARKERS))
        self.assertIn("GUI.Repaint", ex)
        self.assertIn("UIR.DrawChain", ex)
        self.assertIn("EditorLoop", ex)

    def test_unity_preset_keeps_explicit_marker_and_unions_excludes(self):
        mf, ex = resolve_draw_filters(
            "unity_game_rendering",
            marker_filter="ForwardOpaque",
            exclude_markers=["MyNoise"],
        )
        self.assertEqual(mf, "ForwardOpaque")
        self.assertIn("GUI.Repaint", ex)
        self.assertIn("MyNoise", ex)

    def test_unknown_preset_raises(self):
        with self.assertRaises(ValueError):
            resolve_draw_filters("not_a_preset")


class TestDecodeMesh(unittest.TestCase):
    def test_sv_position_first(self):
        # two vertices, stride 16, SV_Position only
        v0 = struct.pack("<ffff", -1.0, 1.0, 0.5, 1.0)
        v1 = struct.pack("<ffff", 1.0, -1.0, 0.25, 2.0)
        verts = decode_position_vertices(v0 + v1, stride=16, count=2)
        self.assertEqual(verts[0], [-1.0, 1.0, 0.5, 1.0])
        self.assertEqual(ndc_xy(verts[1]), [0.5, -0.5])

    def test_short_buffer_stops(self):
        data = struct.pack("<ffff", 0.0, 0.0, 0.0, 1.0)
        verts = decode_position_vertices(data, stride=16, count=8)
        self.assertEqual(len(verts), 1)

    def test_zero_stride(self):
        self.assertEqual(decode_position_vertices(b"xxxx", 0, 4), [])


class TestMeshAddressing(unittest.TestCase):
    def _load_mesh_address(self):
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[1]
            / "renderdoc_extension"
            / "utils"
            / "mesh_address.py"
        )
        spec = importlib.util.spec_from_file_location("rd_mesh_address", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_indexed_draw_skips_index_offset(self):
        addr = self._load_mesh_address()
        # IB starts at 8, draw starts at index 3, stride 2 → skip 6 extra bytes
        self.assertEqual(addr.index_fetch_offset(8, 3, 2), 14)

    def test_indexed_vertices_use_base_vertex_not_linear(self):
        addr = self._load_mesh_address()
        # sampled indices 5,6,6 plus baseVertex 10 → vertices 15,16,16
        self.assertEqual(addr.vertex_ids_from_indices([5, 6, 6], 10), [15, 16, 16])

    def test_non_indexed_uses_vertex_offset(self):
        addr = self._load_mesh_address()
        # attr 4 + vb 32 + vertexOffset 2 * stride 16 = 68
        self.assertEqual(addr.vertex_fetch_offset(4, 32, 2, 16), 68)

    def test_decode_vertices_at_ids_from_span(self):
        addr = self._load_mesh_address()
        # three verts packed as float4, we want ids 1 and 2 from a span starting at 0
        v0 = struct.pack("<ffff", 0.0, 0.0, 0.0, 1.0)
        v1 = struct.pack("<ffff", 1.0, 2.0, 3.0, 1.0)
        v2 = struct.pack("<ffff", 4.0, 5.0, 6.0, 1.0)
        decoded = addr.decode_attr_at_vertex_ids(
            v0 + v1 + v2, stride=16, vertex_ids=[1, 2], vmin=0, nfloats=4
        )
        self.assertEqual(decoded[0]["vertex_index"], 1)
        self.assertEqual(decoded[0]["values"], [1.0, 2.0, 3.0, 1.0])
        self.assertEqual(decoded[1]["values"], [4.0, 5.0, 6.0, 1.0])

    def test_vertex_span_ignores_negatives_and_caps_sparse(self):
        addr = self._load_mesh_address()
        self.assertEqual(addr.vertex_span([-2, 1, 2]), (1, 2))
        self.assertIsNone(addr.vertex_span([-1, -4]))
        # 0 and 10000 is too sparse for 2 ids (max_span = max(32, 256) = 256)
        self.assertIsNone(addr.vertex_span([0, 10000]))
        self.assertEqual(addr.vertex_span([10, 12, 11]), (10, 3))

    def test_sample_vertices_span_vs_each(self):
        addr = self._load_mesh_address()
        # verts 0,1,2 as float4
        packed = b"".join(
            struct.pack("<ffff", float(i), 0.0, 0.0, 1.0) for i in range(3)
        )
        calls = []

        def get_bytes(offset, length):
            calls.append((offset, length))
            return packed[offset : offset + length]

        # dense 1,2 → one span fetch starting at vertex 1
        verts = addr.sample_vertices_at_ids(
            [1, 2], stride=16, nfloats=4, attr_name="POSITION",
            get_bytes=get_bytes, attr_byte_offset=0, vb_byte_offset=0,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(verts[0]["vertex_index"], 1)
        self.assertEqual(verts[0]["values"][0], 1.0)
        self.assertEqual(verts[1]["values"][0], 2.0)

        calls[:] = []
        # negative id is not fetched; positive neighbour still is
        verts = addr.sample_vertices_at_ids(
            [-1, 2], stride=16, nfloats=4, attr_name="POSITION",
            get_bytes=get_bytes, attr_byte_offset=0, vb_byte_offset=0,
        )
        self.assertIsNone(verts[0]["values"])
        self.assertEqual(verts[1]["vertex_index"], 2)
        self.assertEqual(verts[1]["values"][0], 2.0)


class _PixelValue:
    def __init__(self, rgba):
        self.floatValue = rgba


class _ModValue:
    def __init__(self, rgba, depth, stencil, valid=True):
        self.col = _PixelValue(rgba)
        self.depth = depth
        self.stencil = stencil
        self._valid = valid

    def IsValid(self):
        return self._valid


class _PixelMod:
    def __init__(self, passed, **kw):
        self._passed = passed
        self.eventId = kw.get("eventId", 10)
        self.fragIndex = 0
        self.primitiveID = 2
        self.preMod = _ModValue((0, 0, 0, 1), 1.0, 0)
        self.shaderOut = _ModValue((1, 0, 0, 1), 0.5, 0)
        self.postMod = _ModValue((1, 0, 0, 1), 0.5, 0)
        self.depthTestFailed = not passed
        self.stencilTestFailed = False
        self.backfaceCulled = False
        self.scissorClipped = False
        self.shaderDiscarded = False
        self.depthClipped = False
        self.viewClipped = False
        self.sampleMasked = False
        self.unboundPS = False
        self.predicationSkipped = False
        self.directShaderWrite = False

    def Passed(self):
        return self._passed


class TestPixelHistoryHelpers(unittest.TestCase):
    def test_serialize_pass_and_fail(self):
        ok = serialize_pixel_modification(_PixelMod(True, eventId=42))
        self.assertTrue(ok["passed"])
        self.assertEqual(ok["event_id"], 42)
        self.assertEqual(ok["shader_out"]["color"][0], 1.0)
        self.assertFalse(ok["failed"]["depth"])

        bad = serialize_pixel_modification(_PixelMod(False))
        self.assertFalse(bad["passed"])
        self.assertTrue(bad["failed"]["depth"])

    def test_cap_history(self):
        events = [{"passed": i % 2 == 0} for i in range(50)]
        out = cap_history(events, max_events=32)
        self.assertEqual(out["count"], 50)
        self.assertEqual(out["returned"], 32)
        self.assertTrue(out["truncated"])
        self.assertEqual(out["passing"], 16)


class TestInvisiblePipeline(unittest.TestCase):
    def test_healthy_emits_pass(self):
        pipe = {
            "rasterizer": {
                "cull_mode": "Back",
                "viewport": {"width": 1920, "height": 1080},
            },
            "blend": {"targets": [{"index": 0, "write_mask": 15}]},
        }
        report = run_deterministic({"total_gpu_ms": 10.0, "fps_target_ms": 16.67}, pipeline=pipe)
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules.get("invisible_pipeline"), CheckStatus.PASS)
        self.assertNotIn("color_write_disabled", rules)

    def test_write_mask_zero(self):
        pipe = {"blend": {"targets": [{"index": 0, "write_mask": 0}]}}
        checks = {c.rule: c for c in check_invisible_pipeline(pipe)}
        self.assertEqual(checks["color_write_disabled"].status, CheckStatus.FAIL)

    def test_missing_write_mask_is_skip_not_fail(self):
        checks = check_invisible_pipeline({"blend": {"targets": [{"index": 0}]}})
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].status, CheckStatus.SKIP)
        self.assertNotIn("color_write_disabled", {c.rule for c in checks})

    def test_cull_plus_partial_blend_does_not_claim_write_mask(self):
        checks = check_invisible_pipeline({
            "rasterizer": {"cull_mode": "Back"},
            "blend": {"targets": [{"index": 0}]},
        })
        by_rule = {c.rule: c for c in checks}
        self.assertEqual(by_rule["invisible_pipeline"].status, CheckStatus.PASS)
        self.assertNotIn("write_mask", by_rule["invisible_pipeline"].expected)

    def test_cull_front_and_back(self):
        pipe = {"rasterizer": {"cull_mode": "CullMode.FrontAndBack"}}
        checks = {c.rule: c for c in check_invisible_pipeline(pipe)}
        self.assertEqual(checks["cull_all"].status, CheckStatus.FAIL)

    def test_empty_viewport(self):
        pipe = {"rasterizer": {"viewport": {"width": 0, "height": 1080}}}
        checks = {c.rule: c for c in check_invisible_pipeline(pipe)}
        self.assertEqual(checks["viewport_empty"].status, CheckStatus.FAIL)

    def test_empty_scissor_when_enabled(self):
        pipe = {
            "rasterizer": {
                "scissor": {"enabled": True, "width": 0, "height": 0},
            }
        }
        checks = {c.rule: c for c in check_invisible_pipeline(pipe)}
        self.assertEqual(checks["scissor_empty"].status, CheckStatus.FAIL)

    def test_empty_pipeline_no_checks(self):
        self.assertEqual(check_invisible_pipeline({}), [])

    def test_partial_pipeline_skips_not_false_pass(self):
        """Missing inspectable raster/blend fields must not emit a PASS."""
        checks = check_invisible_pipeline({"shaders": {"pixel": {}}})
        self.assertTrue(checks, "expected a SKIP, not an empty list")
        self.assertEqual(checks[0].rule, "invisible_pipeline")
        self.assertEqual(checks[0].status, CheckStatus.SKIP)

        empty_sections = check_invisible_pipeline(
            {"rasterizer": {}, "depth_stencil": {}, "blend": {}}
        )
        self.assertEqual(empty_sections[0].status, CheckStatus.SKIP)
        self.assertNotEqual(empty_sections[0].status, CheckStatus.PASS)

    def test_partial_pipeline_skip_in_l1_report(self):
        report = run_deterministic(
            {"total_gpu_ms": 10.0, "fps_target_ms": 16.67},
            pipeline={"shaders": {"pixel": {"resources": [{"slot": 0}]}}},
        )
        rules = {c.rule: c.status for c in report.checks}
        self.assertEqual(rules.get("invisible_pipeline"), CheckStatus.SKIP)
        self.assertNotEqual(rules.get("invisible_pipeline"), CheckStatus.PASS)


class TestRequestHandlerRegistration(unittest.TestCase):
    def _load_handler(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "renderdoc_extension" / "request_handler.py"
        spec = importlib.util.spec_from_file_location("rd_request_handler", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.RequestHandler

    def test_new_methods_are_registered(self):
        RequestHandler = self._load_handler()

        class FakeFacade:
            pass

        handler = RequestHandler(FakeFacade())
        for name in (
            "pick_pixel",
            "get_pixel_history",
            "get_mesh_data",
            "get_resource_usage",
            "close_capture",
            "save_capture",
            "embed_dependencies",
            "remove_dependencies",
            "list_capture_formats",
            "convert_capture",
            "set_event",
            "export_texture",
            "export_render_target",
            "get_thumbnail",
            "export_buffer",
            "debug_pixel",
            "debug_vertex",
            "debug_thread",
            "list_resources",
            "get_resource",
            "replace_resource",
            "restore_resource",
            "restore_all_replacements",
            "get_texture_stats",
            "list_shader_encodings",
            "list_shaders",
            "shader_map",
            "search_shaders",
            "compile_custom_shader",
            "get_counters",
            "get_snapshot",
            "list_sections",
            "get_section",
            "write_section",
        ):
            self.assertIn(name, handler._methods)

    def test_pick_pixel_requires_xy(self):
        RequestHandler = self._load_handler()

        class FakeFacade:
            def pick_pixel(self, *a, **k):
                return {"ok": True}

        handler = RequestHandler(FakeFacade())
        resp = handler.handle({"id": 1, "method": "pick_pixel", "params": {"event_id": 1}})
        self.assertIn("error", resp)


if __name__ == "__main__":
    unittest.main()
