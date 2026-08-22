"""GPU-free tests for in-capture write tools (session/export/debug/resource)."""

import importlib.util
import unittest
from pathlib import Path

from mcp_server.bridge.client import (
    DEBUG_TIMEOUT,
    DEFAULT_TIMEOUT,
    RenderDocBridge,
)


ROOT = Path(__file__).resolve().parents[1]
EXT_UTILS = ROOT / "renderdoc_extension" / "utils"


def _load(name, rel):
    path = EXT_UTILS / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_handler():
    path = ROOT / "renderdoc_extension" / "request_handler.py"
    spec = importlib.util.spec_from_file_location("rd_request_handler_write", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RequestHandler


class TestBridgeTimeout(unittest.TestCase):
    def test_debug_methods_get_120s(self):
        b = RenderDocBridge()
        self.assertEqual(b.timeout_for("get_draw_calls"), DEFAULT_TIMEOUT)
        self.assertEqual(b.timeout_for("debug_pixel"), DEBUG_TIMEOUT)
        self.assertEqual(b.timeout_for("debug_vertex"), DEBUG_TIMEOUT)
        self.assertEqual(b.timeout_for("debug_thread"), DEBUG_TIMEOUT)
        self.assertEqual(b.timeout_for("replay_event"), DEBUG_TIMEOUT)
        self.assertEqual(b.timeout_for("replace_shader"), DEBUG_TIMEOUT)
        self.assertEqual(b.timeout_for("compile_shader"), DEBUG_TIMEOUT)
        self.assertEqual(b.timeout_for("pick_pixel"), DEBUG_TIMEOUT)
        self.assertEqual(b.timeout_for("debug_pixel", timeout=9), 9.0)


class TestExportOpts(unittest.TestCase):
    def test_normalize_and_resolve(self):
        opts = _load("rd_export_opts", "export_opts.py")
        self.assertEqual(opts.normalize_file_type("JPEG"), "jpg")
        self.assertEqual(opts.normalize_file_type("png"), "png")
        with self.assertRaises(ValueError):
            opts.normalize_file_type("gif")
        path = opts.resolve_export_path(None, "tex", "ResourceId::12", "png")
        self.assertTrue(path.endswith("tex_ResourceId__12.png"))
        self.assertIn("renderdoc_mcp", path)
        self.assertEqual(
            opts.resolve_export_path("C:/tmp/out.png", "tex", "1", "png"),
            "C:/tmp/out.png",
        )


class TestDebugTrace(unittest.TestCase):
    def test_clamps_and_anomalies(self):
        tr = _load("rd_debug_trace", "debug_trace.py")
        self.assertEqual(tr.clamp_max_steps(0), 64)
        self.assertEqual(tr.clamp_max_steps(9999), 256)
        self.assertEqual(tr.clamp_last_n(100), 32)

        class _Val:
            def __init__(self):
                self.f32v = [float("nan"), 0.0, 0.0, 1.0]

        class _Var:
            def __init__(self, name):
                self.name = name
                self.value = _Val()

        class _Ch:
            def __init__(self):
                self.after = _Var("SV_Target0")
                self.before = None

        class _St:
            def __init__(self, step, flags=""):
                self.stepIndex = step
                self.nextInstruction = step
                self.flags = flags
                self.changes = [_Ch()]

        out = tr.cap_states([_St(i, "NaN") for i in range(20)], last_n=8)
        self.assertEqual(out["count"], 20)
        self.assertEqual(out["returned"], 8)
        self.assertTrue(out["truncated"])
        self.assertIn("nan", out["anomalies"])
        self.assertIn("nan_or_inf", out["anomalies"])
        self.assertEqual(out["final_variables"][0]["name"], "SV_Target0")


class TestCounterValue(unittest.TestCase):
    def test_plain_and_struct(self):
        cv = _load("rd_counters", "counters.py")
        self.assertEqual(cv.counter_value(3), 3)
        self.assertEqual(cv.counter_value(1.5), 1.5)
        self.assertIsNone(cv.counter_value(None))

        class _U64:
            u64 = 42
            d = None
            f = None
            u32 = None
            i64 = None
            i32 = None

        self.assertEqual(cv.counter_value(_U64()), 42)

        class _D:
            u64 = None
            d = 0.25
            f = None
            u32 = None
            i64 = None
            i32 = None

        self.assertEqual(cv.counter_value(_D()), 0.25)


class TestWriteHandler(unittest.TestCase):
    def test_save_capture_requires_path(self):
        class Fake:
            def save_capture(self, path):
                return {"path": path}

        handler = _load_handler()(Fake())
        resp = handler.handle({"id": 1, "method": "save_capture", "params": {}})
        self.assertIn("error", resp)

    def test_set_event_and_replace_resource(self):
        calls = {}

        class Fake:
            def set_event(self, event_id, force=True):
                calls["set_event"] = (event_id, force)
                return {"event_id": event_id}

            def replace_resource(self, original, replacement):
                calls["replace"] = (original, replacement)
                return {"ok": True}

            def debug_thread(self, *a, **k):
                calls["debug_thread"] = (a, k)
                return {"available": False}

        handler = _load_handler()(Fake())
        resp = handler.handle(
            {"id": 2, "method": "set_event", "params": {"event_id": 9}}
        )
        self.assertEqual(resp["result"]["event_id"], 9)
        self.assertEqual(calls["set_event"], (9, True))

        resp = handler.handle(
            {
                "id": 3,
                "method": "replace_resource",
                "params": {
                    "original_resource_id": "ResourceId::1",
                    "replacement_resource_id": "ResourceId::2",
                },
            }
        )
        self.assertEqual(resp["result"]["ok"], True)

        resp = handler.handle(
            {
                "id": 4,
                "method": "debug_thread",
                "params": {"event_id": 1, "group_x": 0, "group_y": 0, "group_z": 0},
            }
        )
        self.assertIn("error", resp)

    def test_export_buffer_and_get_section_validation(self):
        class Fake:
            def export_buffer(self, resource_id, path=None, offset=0, length=0):
                return {"path": path or "auto", "resource_id": resource_id}

            def get_section(self, index=None, name=None, max_bytes=4096):
                return {"index": index, "name": name, "max_bytes": max_bytes}

        handler = _load_handler()(Fake())
        resp = handler.handle({"id": 5, "method": "export_buffer", "params": {}})
        self.assertIn("error", resp)
        resp = handler.handle(
            {"id": 6, "method": "export_buffer", "params": {"resource_id": "1"}}
        )
        self.assertEqual(resp["result"]["resource_id"], "1")
        resp = handler.handle({"id": 7, "method": "get_section", "params": {}})
        self.assertIn("error", resp)
        resp = handler.handle(
            {"id": 8, "method": "get_section", "params": {"name": "thumbnail"}}
        )
        self.assertEqual(resp["result"]["name"], "thumbnail")


class TestMcpToolNames(unittest.TestCase):
    def test_server_defines_write_tools(self):
        src = (ROOT / "mcp_server" / "server.py").read_text(encoding="utf-8")
        for name in (
            "def close_capture",
            "def save_capture",
            "def set_event",
            "def export_texture",
            "def export_render_target",
            "def get_thumbnail",
            "def export_buffer",
            "def debug_pixel",
            "def debug_vertex",
            "def debug_thread",
            "def list_resources",
            "def replace_resource",
            "def restore_all_replacements",
            "def compile_custom_shader",
            "def get_counters",
            "def get_snapshot",
            "def list_sections",
            "def get_section",
            "def write_section",
            "def embed_dependencies",
            "def convert_capture",
        ):
            self.assertIn(name, src)
        self.assertIn('compile_flags: Literal["default", "debug"]', src)


class TestTexStats(unittest.TestCase):
    def test_channels_nan_and_histogram(self):
        ts = _load("rd_tex_stats", "tex_stats.py")

        class _Pix:
            def __init__(self, f, u=None, i=None):
                self.floatValue = f
                self.uintValue = u
                self.intValue = i

        ch = ts.channels_from_pixel(_Pix([float("nan"), 0.0, 1.0, 2.0], [1, 2, 3, 4]))
        self.assertEqual(ch["uint"], [1, 2, 3, 4])
        self.assertIn("nan", ts.nan_inf_flags(ch["float"]))
        self.assertIsNone(ts.histogram_range(ch["float"], [0.0, 1.0, 2.0, 3.0]))
        self.assertEqual(ts.histogram_range([0.0, 1.0], [2.0, 4.0]), (0.0, 4.0))
        self.assertEqual(ts.histogram_channels(False), (True, True, True, False))
        reduced = ts.reduce_histogram(list(range(256)))
        self.assertEqual(len(reduced), 16)
        self.assertEqual(sum(reduced), sum(range(256)))

    def test_none_pixel_is_empty_channels(self):
        ts = _load("rd_tex_stats_none", "tex_stats.py")
        ch = ts.channels_from_pixel(None)
        self.assertEqual(ch, {"float": None, "uint": None, "int": None})


class TestSections(unittest.TestCase):
    def test_load_cap_and_type_enum(self):
        sec = _load("rd_sections", "sections.py")
        self.assertTrue(sec.section_load_allowed(100))
        self.assertTrue(sec.section_load_allowed(None))
        self.assertFalse(sec.section_load_allowed(sec.SECTION_LOAD_CAP + 1))
        self.assertEqual(sec.section_type_enum_name("notes"), "Notes")
        with self.assertRaises(ValueError):
            sec.section_type_enum_name("framecapture")
        self.assertEqual(sec.clamp_section_json_bytes(999999), sec.SECTION_JSON_CAP)
        self.assertEqual(sec.encode_section_contents("hi"), b"hi")
        with self.assertRaises(ValueError):
            sec.encode_section_contents(b"x" * (sec.SECTION_WRITE_CAP + 1))


class TestCompileOpts(unittest.TestCase):
    def test_presets(self):
        opts = _load("rd_compile_opts", "compile_opts.py")
        self.assertEqual(opts.resolve_compile_flags(None), [])
        self.assertEqual(opts.resolve_compile_flags("default"), [])
        debug = opts.resolve_compile_flags("debug")
        names = {p["name"] for p in debug}
        self.assertIn("D3DCOMPILE_DEBUG", names)
        self.assertIn("D3DCOMPILE_SKIP_OPTIMIZATION", names)
        with self.assertRaises(ValueError):
            opts.resolve_compile_flags("fast")
        custom = opts.resolve_compile_flags([{"name": "FOO", "value": "1"}])
        self.assertEqual(custom, [{"name": "FOO", "value": "1"}])


class TestCaptureFileHandler(unittest.TestCase):
    def test_convert_requires_filename(self):
        class Fake:
            def convert_capture(self, filename, filetype="rdc"):
                return {"path": filename, "filetype": filetype}

            def embed_dependencies(self):
                return {"embedded": True}

        handler = _load_handler()(Fake())
        resp = handler.handle({"id": 12, "method": "convert_capture", "params": {}})
        self.assertIn("error", resp)
        resp = handler.handle(
            {
                "id": 13,
                "method": "convert_capture",
                "params": {"filename": "out.xml", "filetype": "xml"},
            }
        )
        self.assertEqual(resp["result"]["path"], "out.xml")
        resp = handler.handle({"id": 14, "method": "embed_dependencies", "params": {}})
        self.assertTrue(resp["result"]["embedded"])


class TestWriteSectionHandler(unittest.TestCase):
    def test_write_section_requires_name_and_contents(self):
        class Fake:
            def write_section(self, name, contents, section_type="unknown"):
                return {"name": name, "bytes": len(contents), "type": section_type}

        handler = _load_handler()(Fake())
        resp = handler.handle({"id": 9, "method": "write_section", "params": {}})
        self.assertIn("error", resp)
        resp = handler.handle(
            {"id": 10, "method": "write_section", "params": {"name": "notes"}}
        )
        self.assertIn("error", resp)
        resp = handler.handle(
            {
                "id": 11,
                "method": "write_section",
                "params": {"name": "notes", "contents": "hello"},
            }
        )
        self.assertEqual(resp["result"]["name"], "notes")
        self.assertEqual(resp["result"]["bytes"], 5)


class TestReplaceResourceNote(unittest.TestCase):
    def test_server_doc_is_not_replay_only(self):
        src = (ROOT / "mcp_server" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("Replay-time only", src)
        self.assertIn("RegisterReplacement", src)
        self.assertIn("GetMinMax", src)
        self.assertIn("WriteSection", src)

    def test_replace_shader_registers_after_blockinvoke(self):
        src = (
            ROOT / "renderdoc_extension" / "services" / "shader_edit_service.py"
        ).read_text(encoding="utf-8")
        body = src.split("def replace_shader", 1)[1].split("def remove_shader_replacement", 1)[0]
        invoke_at = body.find("self._invoke(callback)")
        register_at = body.find("RegisterReplacement")
        self.assertGreater(invoke_at, 0)
        self.assertGreater(register_at, invoke_at)

    def test_parse_resource_id_does_not_assign_private_id(self):
        src = (ROOT / "renderdoc_extension" / "utils" / "parsers.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("rid.id =", src)
        self.assertIn("resolve_live", src)

    def test_stats_never_scan_texture_bytes(self):
        src = (
            ROOT / "renderdoc_extension" / "services" / "resource_service.py"
        ).read_text(encoding="utf-8")
        stats = src.split("def get_texture_stats", 1)[1].split("def get_texture_info", 1)[0]
        self.assertNotIn("controller.GetTextureData", stats)
        self.assertNotIn("bytearray(", stats)
        self.assertIn("GetMinMax", stats)
        self.assertIn("GetHistogram", stats)

    def test_debug_pixel_has_no_wrong_signature_fallback(self):
        src = (
            ROOT / "renderdoc_extension" / "services" / "debug_service.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("DebugPixel(int(x), int(y), samp, prim)", src)


class TestSampleVerticesNoneBytes(unittest.TestCase):
    def test_get_bytes_none_does_not_crash(self):
        addr = _load("rd_mesh_address_write", "mesh_address.py")
        verts = addr.sample_vertices_at_ids(
            [0, 1],
            stride=16,
            nfloats=4,
            attr_name="POSITION",
            get_bytes=lambda off, length: None,
            attr_byte_offset=0,
            vb_byte_offset=0,
        )
        self.assertEqual(len(verts), 2)
        self.assertIsNone(verts[0]["values"])
        self.assertIsNone(verts[1]["values"])


if __name__ == "__main__":
    unittest.main()
