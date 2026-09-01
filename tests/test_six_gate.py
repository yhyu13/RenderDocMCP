"""GPU-free tests for the Python 3.6-compatibility gate (renderdoc_extension boundary)."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "six_gate.py"
    spec = importlib.util.spec_from_file_location("rd_six_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSixCompatGate(unittest.TestCase):
    def setUp(self):
        self.gate = _load()

    def test_accepts_clean_36(self):
        src = "def f(a, b=1):\n    return a + b\n"
        self.assertEqual(self.gate.six_compat_errors(src, "m.py"), [])

    def test_accepts_optional_annotation(self):
        src = "from typing import Optional\ndef f(x: Optional[int] = None):\n    return x\n"
        self.assertEqual(self.gate.six_compat_errors(src, "m.py"), [])

    def test_rejects_union_annotation(self):
        # `int | None` is parse-legal even under py3.6 (a bitwise-or), but is a
        # 3.10+ type-union semantics — the embedded 3.6 interpreter can't use it.
        src = "def f(x: int | None) -> None:\n    return None\n"
        errors = self.gate.six_compat_errors(src, "m.py")
        self.assertTrue(errors)
        self.assertIn("annotation union", errors[0][1])

    def test_rejects_walrus(self):
        src = "x = 1\nif (y := f()):\n    pass\n"
        errors = self.gate.six_compat_errors(src, "m.py")
        self.assertTrue(errors)

    def test_rejects_match_statement(self):
        src = "match x:\n    case 1:\n        return\n"
        errors = self.gate.six_compat_errors(src, "m.py")
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
