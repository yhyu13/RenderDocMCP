"""Red-capable tests for the live OpenGL capture ResourceId / CaptureFile bugs."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT_UTILS = ROOT / "renderdoc_extension" / "utils"


def _load(name, rel):
    path = EXT_UTILS / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Rid:
    """Stand-in for a real SWIG ResourceId: str() works, .id assignment does not."""

    def __init__(self, n):
        self._n = int(n)

    def __str__(self):
        return "ResourceId::%d" % self._n

    def __eq__(self, other):
        return isinstance(other, _Rid) and other._n == self._n


class TestNumericId(unittest.TestCase):
    def setUp(self):
        self.rid = _load("rd_resource_id", "resource_id.py")

    def test_parses_common_forms(self):
        self.assertEqual(self.rid.numeric_id("ResourceId::56"), 56)
        self.assertEqual(self.rid.numeric_id("56"), 56)
        self.assertEqual(self.rid.numeric_id("ResourceId::1000000000000000407"), 1000000000000000407)

    def test_null_is_null(self):
        self.assertTrue(self.rid.is_null_id("ResourceId::0"))
        self.assertTrue(self.rid.is_null_id("0"))
        self.assertFalse(self.rid.is_null_id("ResourceId::56"))

    def test_ids_equal_rejects_null_null(self):
        """Live bug: find_draws_by_resource matched Hull because Null == Null."""
        self.assertFalse(self.rid.ids_equal("ResourceId::0", "ResourceId::0"))
        self.assertFalse(self.rid.ids_equal("ResourceId::56", "ResourceId::0"))
        self.assertTrue(self.rid.ids_equal("ResourceId::56", "56"))


class TestEncodingAndFormat(unittest.TestCase):
    def setUp(self):
        self.rid = _load("rd_resource_id_enc", "resource_id.py")

    def test_encoding_prefers_name_over_int(self):
        class _Enc:
            name = "GLSL"

            def __str__(self):
                return "2"

        self.assertEqual(self.rid.shader_encoding_name(_Enc()), "GLSL")
        self.assertEqual(self.rid.shader_encoding_name("ShaderEncoding.HLSL"), "HLSL")
        self.assertEqual(self.rid.shader_encoding_name(2), "GLSL")
        self.assertEqual(self.rid.shader_encoding_name("2"), "GLSL")
        self.assertEqual(self.rid.shader_encoding_name(7), "HLSL")

    def test_format_skips_swig_pointer(self):
        class _Fmt:
            def Name(self):
                return "R32G32B32A32_FLOAT"

            def __str__(self):
                return "<Swig Object of type 'ResourceFormat *' at 0x1>"

        self.assertEqual(self.rid.resource_format_name(_Fmt()), "R32G32B32A32_FLOAT")

        class _Bare:
            def __str__(self):
                return "<Swig Object of type 'ResourceFormat *' at 0x1>"

        self.assertEqual(self.rid.resource_format_name(_Bare()), "")

    def test_sane_mip_count_drops_233(self):
        self.assertIsNone(self.rid.sane_mip_count(233))
        self.assertEqual(self.rid.sane_mip_count(233, fallback=1), 1)
        self.assertEqual(self.rid.sane_mip_count(4), 4)


class TestResolveByScan(unittest.TestCase):
    def test_scan_finds_live_object_not_forged_zero(self):
        rid_mod = _load("rd_resource_id_scan", "resource_id.py")

        class Tex:
            def __init__(self, n):
                self.resourceId = _Rid(n)

        def scan(items, target_str):
            target = rid_mod.numeric_id(target_str)
            for item in items:
                if rid_mod.numeric_id(str(item.resourceId)) == target:
                    return item.resourceId
            return None

        found = scan([Tex(56), Tex(160)], "ResourceId::56")
        self.assertEqual(str(found), "ResourceId::56")
        missing = scan([Tex(56)], "ResourceId::125")
        self.assertIsNone(missing)


class TestCaptureAccessModule(unittest.TestCase):
    def test_pick_uses_replay_manager(self):
        path = EXT_UTILS / "capture_access.py"
        spec = importlib.util.spec_from_file_location("rd_capture_access", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        handle = object()

        class Replay:
            def GetCaptureAccess(self):
                return handle

            def GetCaptureFile(self):
                return None

        class Ctx:
            def IsCaptureLoaded(self):
                return True

            def GetCaptureFile(self):
                raise AttributeError("no")

            def Replay(self):
                return Replay()

        picked, source = mod.pick_capture_access(Ctx())
        self.assertIs(picked, handle)
        self.assertEqual(source, "replay.GetCaptureAccess")


class TestCaptureAccessPicker(unittest.TestCase):
    def test_prefers_replay_manager_over_missing_ctx_method(self):
        """Live bug: ctx.GetCaptureFile() is missing/None on MCP LoadCapture."""
        handle = object()

        class Replay:
            def GetCaptureAccess(self):
                return handle

            def GetCaptureFile(self):
                return None

        class Ctx:
            def GetCaptureFile(self):
                raise AttributeError("no GetCaptureFile on CaptureContext")

            def Replay(self):
                return Replay()

        picked = None
        ctx = Ctx()
        try:
            picked = ctx.GetCaptureFile()
        except Exception:
            picked = None
        self.assertIsNone(picked)
        replay = ctx.Replay()
        picked = replay.GetCaptureFile() or replay.GetCaptureAccess()
        self.assertIs(picked, handle)


if __name__ == "__main__":
    unittest.main()
