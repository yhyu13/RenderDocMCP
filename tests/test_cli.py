"""Tests for the CLI entry point (python -m rdc_harness)."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from rdc_harness.__main__ import main


PAYLOAD = {
    "total_gpu_ms": 22.0,
    "fps_target_ms": 16.67,
    "api_stats": {"draw_calls": 5200},
}


class TestCli(unittest.TestCase):
    def test_cli_strips_bom_and_emits_red_flags(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "wb") as f:
            f.write(b"\xef\xbb\xbf")  # UTF-8 BOM
            f.write(json.dumps(PAYLOAD).encode("utf-8"))
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main([path])
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            rules = {f["rule"] for f in out["red_flags"]}
            self.assertIn("fps_budget", rules)
            self.assertIn("draw_count", rules)
        finally:
            os.remove(path)

    def test_cli_reads_stdin(self):
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(PAYLOAD))):
            with redirect_stdout(buf):
                rc = main(["-"])
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertIn("fps_budget", {f["rule"] for f in out["red_flags"]})


if __name__ == "__main__":
    unittest.main()
