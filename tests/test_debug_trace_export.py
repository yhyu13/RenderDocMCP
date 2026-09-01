"""GPU-free tests for debug_trace_export (full trajectory dump to file)."""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from mcp_server.bridge.client import DEBUG_TIMEOUT, RenderDocBridge


ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Val:
    def __init__(self, seq, attr="f32v"):
        setattr(self, attr, list(seq))


class _Var:
    def __init__(self, name, seq, attr="f32v"):
        self.name = name
        self.value = _Val(seq, attr)


class _Ch:
    def __init__(self, before, after):
        self.before = before
        self.after = after


class _St:
    def __init__(self, step, changes, flags=""):
        self.stepIndex = step
        self.nextInstruction = step + 1
        self.flags = flags
        self.changes = changes


class TestSerializeStateFull(unittest.TestCase):
    def setUp(self):
        self.tr = _load("rd_debug_trace_export", "renderdoc_extension/utils/debug_trace.py")

    def test_keeps_full_width_values_and_both_sides(self):
        st = _St(
            3,
            [
                _Ch(
                    _Var("temp", [1.5, float("nan"), float("inf"), float("-inf"), 7.5]),
                    _Var("temp", [0.25, 0.5, 0.75]),
                )
            ],
            flags="",
        )
        out = self.tr.serialize_state_full(st)
        self.assertEqual(out["step"], 3)
        self.assertEqual(out["next_instruction"], 4)
        ch = out["changes"][0]
        self.assertEqual(ch["name"], "temp")
        self.assertEqual(
            ch["before"], [1.5, "NaN", "Inf", "-Inf", 7.5]
        )
        self.assertEqual(ch["after"], [0.25, 0.5, 0.75])

    def test_uint_and_int_vectors_pass_through(self):
        st = _St(
            0,
            [_Ch(_Var("idx", [10, 20], "u32v"), _Var("idx", [30, 40], "s32v"))],
        )
        ch = self.tr.serialize_state_full(st)["changes"][0]
        self.assertEqual(ch["before"], [10, 20])
        self.assertEqual(ch["after"], [30, 40])

    def test_none_before_keeps_name_from_after(self):
        st = _St(1, [_Ch(None, _Var("out", [1.0]))])
        ch = self.tr.serialize_state_full(st)["changes"][0]
        self.assertIsNone(ch["before"])
        self.assertEqual(ch["after"], [1.0])


class TestAnomaliesFor(unittest.TestCase):
    def setUp(self):
        self.tr = _load("rd_debug_trace_export", "renderdoc_extension/utils/debug_trace.py")

    def test_dedup_and_combine(self):
        states = [_St(0, [], flags="NaN"), _St(1, [], flags="NaN")]
        finals = [{"name": "out", "value": [float("nan")]}]
        self.assertEqual(self.tr.anomalies_for(states, finals), ["nan", "nan_or_inf"])

    def test_clean(self):
        states = [_St(0, [], flags="")]
        self.assertEqual(self.tr.anomalies_for(states, [{"name": "a", "value": [1.0]}]), [])


class TestWriteTraceFile(unittest.TestCase):
    def setUp(self):
        self.tr = _load("rd_debug_trace_export", "renderdoc_extension/utils/debug_trace.py")
        self.tmp = tempfile.mkdtemp(prefix="rd_trace_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_header_plus_one_state_per_line(self):
        states = [
            _St(0, [_Ch(None, _Var("a", [1.0]))], flags=""),
            _St(1, [_Ch(_Var("a", [1.0]), _Var("a", [2.0]))], flags=""),
        ]
        path = str(Path(self.tmp) / "trace.jsonl")
        written = self.tr.write_trace_file(
            path, states, {"kind": "pixel", "event_id": 9}
        )
        self.assertEqual(written, 2)
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        header = json.loads(lines[0])
        self.assertEqual(header["type"], "header")
        self.assertEqual(header["kind"], "pixel")
        self.assertEqual(header["event_id"], 9)
        self.assertEqual(json.loads(lines[1])["step"], 0)
        self.assertEqual(json.loads(lines[2])["changes"][0]["after"], [2.0])

    def test_creates_missing_parent_dirs(self):
        path = str(Path(self.tmp) / "deep" / "nested" / "trace.jsonl")
        written = self.tr.write_trace_file(path, [], {"kind": "pixel"})
        self.assertEqual(written, 0)
        self.assertTrue(Path(path).is_file())


class TestClampExportLimit(unittest.TestCase):
    def setUp(self):
        self.tr = _load("rd_debug_trace_export", "renderdoc_extension/utils/debug_trace.py")

    def test_none_bounded_by_hard_ceiling(self):
        self.assertEqual(self.tr.clamp_export_limit(None), 1000000)

    def test_positive_passes_through_and_caps(self):
        self.assertEqual(self.tr.clamp_export_limit(50), 50)
        self.assertEqual(self.tr.clamp_export_limit(99999999), 1000000)

    def test_zero_and_negative_rejected(self):
        for bad in (0, -5):
            with self.assertRaises(ValueError):
                self.tr.clamp_export_limit(bad)


class TestBridgeTimeoutForExport(unittest.TestCase):
    def test_export_walks_the_120s_tier(self):
        b = RenderDocBridge()
        self.assertEqual(b.timeout_for("debug_trace_export"), DEBUG_TIMEOUT)


class TestHandlerDispatchExport(unittest.TestCase):
    def _handler_mod(self):
        path = ROOT / "renderdoc_extension" / "request_handler.py"
        spec = importlib.util.spec_from_file_location("rd_handler_export", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.RequestHandler

    def test_dispatch_passes_params(self):
        calls = {}

        class Fake:
            def debug_trace_export(self, event_id, x, y, **kw):
                calls["args"] = (event_id, x, y)
                calls["kw"] = kw
                return {"available": True, "path": "trace.jsonl"}

        handler = self._handler_mod()(Fake())
        resp = handler.handle(
            {
                "id": 1,
                "method": "debug_trace_export",
                "params": {
                    "event_id": 550,
                    "x": 12,
                    "y": 34,
                    "path": "trace.jsonl",
                    "max_steps": 100,
                },
            }
        )
        self.assertEqual(resp["result"]["available"], True)
        self.assertEqual(calls["args"], (550, 12, 34))
        self.assertEqual(calls["kw"]["path"], "trace.jsonl")
        self.assertEqual(calls["kw"]["max_steps"], 100)

    def test_dispatch_requires_xy(self):
        class Fake:
            def debug_trace_export(self, *a, **k):
                raise AssertionError("must not be called")

        handler = self._handler_mod()(Fake())
        resp = handler.handle(
            {"id": 2, "method": "debug_trace_export", "params": {"event_id": 1}}
        )
        self.assertIn("error", resp)


class TestFinalVariablesFallback(unittest.TestCase):
    def setUp(self):
        self.tr = _load("rd_debug_trace_export", "renderdoc_extension/utils/debug_trace.py")

    def test_uses_before_name_when_after_name_empty(self):
        # Some backends (e.g. GL) leave changes[].after.name empty. final_variables
        # must fall back to the *before* var name (matches summarize_state/serialize_state_full).
        st = _St(2, [_Ch(_Var("out_color", [1.0, 2.0]), _Var("", [1.0, 2.0]))])
        self.assertEqual(
            self.tr.final_variables(st),
            [{"name": "out_color", "value": [1.0, 2.0]}],
        )

    def test_skips_fully_nameless_changes(self):
        st = _St(0, [_Ch(_Var("", [1.0]), _Var("", [2.0]))])
        self.assertEqual(self.tr.final_variables(st), [])


class TestBridgeTimeoutVertexCompute(unittest.TestCase):
    def test_vertex_and_compute_export_on_120s_tier(self):
        b = RenderDocBridge()
        self.assertEqual(b.timeout_for("debug_trace_export_vertex"), DEBUG_TIMEOUT)
        self.assertEqual(b.timeout_for("debug_trace_export_compute"), DEBUG_TIMEOUT)


class TestHandlerDispatchVertexCompute(unittest.TestCase):
    def _handler_mod(self):
        path = ROOT / "renderdoc_extension" / "request_handler.py"
        spec = importlib.util.spec_from_file_location("rd_handler_vc", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.RequestHandler

    def test_vertex_forwards_params(self):
        calls = {}

        class Fake:
            def debug_trace_export_vertex(self, event_id, vertex_id, **kw):
                calls["args"] = (event_id, vertex_id)
                calls["kw"] = kw
                return {"available": True, "path": "v.jsonl"}

        handler = self._handler_mod()(Fake())
        resp = handler.handle(
            {
                "id": 1,
                "method": "debug_trace_export_vertex",
                "params": {
                    "event_id": 550,
                    "vertex_id": 12,
                    "instance": 3,
                    "index": 5,
                    "path": "v.jsonl",
                    "max_steps": 100,
                },
            }
        )
        self.assertEqual(resp["result"]["available"], True)
        self.assertEqual(calls["args"], (550, 12))
        self.assertEqual(calls["kw"]["instance"], 3)
        self.assertEqual(calls["kw"]["index"], 5)
        self.assertEqual(calls["kw"]["path"], "v.jsonl")
        self.assertEqual(calls["kw"]["max_steps"], 100)

    def test_vertex_requires_vertex_id(self):
        class Fake:
            def debug_trace_export_vertex(self, *a, **k):
                raise AssertionError("must not be called")

        handler = self._handler_mod()(Fake())
        resp = handler.handle(
            {"id": 2, "method": "debug_trace_export_vertex", "params": {"event_id": 1}}
        )
        self.assertIn("error", resp)

    def test_compute_forwards_params(self):
        calls = {}

        class Fake:
            def debug_trace_export_compute(self, event_id, *coords, **kw):
                calls["args"] = (event_id, coords)
                calls["kw"] = kw
                return {"available": True, "path": "c.jsonl"}

        handler = self._handler_mod()(Fake())
        resp = handler.handle(
            {
                "id": 3,
                "method": "debug_trace_export_compute",
                "params": {
                    "event_id": 9,
                    "group_x": 1,
                    "group_y": 2,
                    "group_z": 3,
                    "thread_x": 4,
                    "thread_y": 5,
                    "thread_z": 6,
                    "path": "c.jsonl",
                },
            }
        )
        self.assertEqual(resp["result"]["available"], True)
        self.assertEqual(calls["args"], (9, (1, 2, 3, 4, 5, 6)))

    def test_compute_requires_all_coords(self):
        class Fake:
            def debug_trace_export_compute(self, *a, **k):
                raise AssertionError("must not be called")

        handler = self._handler_mod()(Fake())
        resp = handler.handle(
            {"id": 4, "method": "debug_trace_export_compute", "params": {"event_id": 9, "group_x": 1}}
        )
        self.assertIn("error", resp)


if __name__ == "__main__":
    unittest.main()
