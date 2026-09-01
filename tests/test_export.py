"""GPU-free tests for shader-patch export and golden-baseline store."""

import tempfile
import unittest
from pathlib import Path

from rdc_harness import (
    artifacts_from_fix_report,
    build_fix_report,
    check_against_golden,
    load_golden,
    shader_unified_diff,
    write_golden,
    write_shader_patch,
)
from rdc_harness.renderdoc_backend import RenderDocShaderBackend


class TestShaderPatch(unittest.TestCase):
    def test_identical_is_empty(self):
        self.assertEqual(shader_unified_diff("a\n", "a\n"), "")

    def test_writes_hlsl_and_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = write_shader_patch(
                original="float4 main() { return 0; }\n",
                final="float4 main() { return 1; }\n",
                dest_dir=tmp,
                stem="fix",
            )
            self.assertTrue(out["changed"])
            self.assertTrue(Path(out["hlsl_path"]).is_file())
            self.assertTrue(Path(out["patch_path"]).is_file())
            patch = Path(out["patch_path"]).read_text(encoding="utf-8")
            self.assertIn("fix.orig.hlsl", patch)
            self.assertIn("+float4 main() { return 1; }", patch)


class TestGoldenStore(unittest.TestCase):
    def test_roundtrip_and_mismatch(self):
        golden = b"\x00\x00\x00\xff" * 4
        with tempfile.TemporaryDirectory() as tmp:
            meta = write_golden(tmp, "rt0", golden, event_id=7)
            self.assertEqual(meta["bytes"], 16)
            data, loaded = load_golden(tmp, "rt0")
            self.assertEqual(data, golden)
            self.assertEqual(loaded["event_id"], 7)
            ok = check_against_golden(tmp, "rt0", golden)
            self.assertTrue(ok["match"])
            bad = check_against_golden(tmp, "rt0", b"\xff" * 16)
            self.assertFalse(bad["match"])
            self.assertTrue(bad["size_match"])


class TestArtifactsFromReport(unittest.TestCase):
    def test_uses_final_source(self):
        result = {"status": "ok", "source": "fixed\n", "history": []}
        rep = build_fix_report(result=result, original_hlsl="orig\n")
        with tempfile.TemporaryDirectory() as tmp:
            out = artifacts_from_fix_report(rep, "orig\n", tmp, stem="out")
            self.assertEqual(out["status"], "ok")
            self.assertTrue(out["changed"])
            self.assertEqual(Path(out["hlsl_path"]).read_text(encoding="utf-8"), "fixed\n")


class TestBackendCompileFlags(unittest.TestCase):
    def test_forwards_debug_preset(self):
        class Fake:
            def __init__(self):
                self.calls = []

            def call(self, method, params=None):
                self.calls.append((method, params or {}))
                if method == "compile_shader":
                    return {"resource_id": "ResourceId::1", "messages": ""}
                return {}

        bridge = Fake()
        backend = RenderDocShaderBackend(
            bridge=bridge, event_id=1, entry="PSMain", compile_flags="debug"
        )
        backend.compile_shader("float4 main(){return 0;}", "pixel")
        compile = [c for c in bridge.calls if c[0] == "compile_shader"][0]
        self.assertEqual(compile[1]["compile_flags"], "debug")


class TestExportContractNoBytes(unittest.TestCase):
    """The export contract: responses carry string paths / hashes / counts, never raw bytes.

    The harness writes image/buffer bytes to disk; the JSON contract must only
    ever carry a path or metadata, so an agent never loads a multi-MB blob into
    context. This pins that contract on the GPU-free export surface.
    """

    def _assert_no_raw_bytes(self, d):
        for v in d.values():
            self.assertNotIsInstance(v, (bytes, bytearray), "export response embeds raw bytes")
            if isinstance(v, dict):
                self._assert_no_raw_bytes(v)

    def test_shader_patch_paths_are_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = write_shader_patch(
                original="float4 main(){return 0;}\n",
                final="float4 main(){return 1;}\n",
                dest_dir=tmp,
                stem="fix",
            )
            self.assertIsInstance(out["hlsl_path"], str)
            self.assertIsInstance(out["patch_path"], str)
            self.assertIsInstance(out["patch"], str)
            self.assertTrue(out["changed"])
            self._assert_no_raw_bytes(out)

    def test_golden_meta_is_metadata_not_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta = write_golden(tmp, "rt0", b"\xff" * 4, event_id=3)
            self.assertIsInstance(meta["path"], str)
            self.assertIsInstance(meta["meta_path"], str)
            self.assertIsInstance(meta["sha256"], str)
            self.assertEqual(meta["bytes"], 4)
            self._assert_no_raw_bytes(meta)

    def test_artifacts_report_contract(self):
        result = {"status": "ok", "source": "fixed\n", "history": []}
        rep = build_fix_report(result=result, original_hlsl="orig\n")
        with tempfile.TemporaryDirectory() as tmp:
            out = artifacts_from_fix_report(rep, "orig\n", tmp, stem="o")
            self.assertIsInstance(out["hlsl_path"], str)
            self._assert_no_raw_bytes(out)


if __name__ == "__main__":
    unittest.main()
