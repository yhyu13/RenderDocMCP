"""One-command quality gate for RenderDocMCP: py_compile + Py3.6 gate + full suite.

Usage:
    python3 scripts/test_all.py

1. Compiles every .py under mcp_server/, rdc_harness/, renderdoc_extension/
   (syntax only; the extension modules import `renderdoc`, so import-in is not
   attempted here).
2. Runs the Python 3.6-compatibility gate on renderdoc_extension/ (the RenderDoc
   embedded interpreter is 3.6 — no walrus, no `X | Y` annotations).
3. Runs `python -m unittest discover -s tests`.

Exit code is non-zero on any failure.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import six_gate  # noqa: E402


def _pyfiles(subdir):
    return sorted((ROOT / subdir).rglob("*.py"))


def main():
    errors = []

    # 1. py_compile (syntax) — all three source trees.
    for subdir in ("mcp_server", "rdc_harness", "renderdoc_extension"):
        for p in _pyfiles(subdir):
            try:
                compile(p.read_text(encoding="utf-8"), str(p), "exec")
            except SyntaxError as e:
                errors.append("%s: %s" % (p.relative_to(ROOT), e))

    # 2. Python 3.6 gate on the extension (embedded interpreter constraint).
    for p in _pyfiles("renderdoc_extension"):
        for lineno, msg in six_gate.six_compat_errors(
            p.read_text(encoding="utf-8"), str(p)
        ):
            errors.append("%s:%s %s" % (p.relative_to(ROOT), lineno, msg))

    if errors:
        print("QUALITY GATE FAILED:")
        for e in errors:
            print("  -", e)
        return 1
    print("quality gate OK (py_compile + Py3.6 boundary)")

    # 3. Run the test suite.
    rc = subprocess.call(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=str(ROOT),
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
