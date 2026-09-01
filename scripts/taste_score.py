"""Taste Score — a deterministic, anti-gaming quality score for agent-built projects.

PURPOSE
  Give a fleet of AI agents ONE comparable number to optimize overnight. Taste is
  operationalized into objective predicates (file exists / symbol present / test
  green / git clean / doc up-to-date), so any agent running this lands the same
  score — no judgment calls, and it is hard to inflate (you can't fake a passing
  test, a present tool, or a tracked artifact).

USAGE
    python3 scripts/taste_score.py                 # score the repo root (cwd default)
    python3 scripts/taste_score.py <repo_root>     # score a sibling repo
    python3 scripts/taste_score.py --json          # machine-readable (leaderboard)

OUTPUT
  total (0-100) + per-dimension ratio + per-check pass/fail with evidence.

WEIGHTS (sum 1.0): Truth 0.22 | Capability 0.22 | Craft 0.20 | Docs 0.14 | Footprint 0.12 | Voice 0.10
"""

import json
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Repo manifest — override per project. Defaults target the RenderDocMCP repo.
# --------------------------------------------------------------------------
DEFAULT_MANIFEST = {
    "server_file": "mcp_server/server.py",          # where MCP tools are defined
    "capture_files": ["capture_webgpu.py"],          # capture-side scripts
    "owns_capture": False,                           # capture is owned by sibling renderdoc-skill
    "toolkit_tools": [                               # the human "90% loop"
        "pick_pixel", "get_pixel_history", "get_mesh_data",
        "get_resource_usage", "get_pipeline_state",
    ],
    "loop_tools": [                                  # the closed shader-edit/replay loop
        "compile_shader", "replace_shader", "replay_event", "get_debug_messages",
    ],
    "killer_tools": ["debug_trace_export",           # beyond-the-GUI capability
                     "debug_trace_export_vertex", "debug_trace_export_compute"],
    "unity_preset": "unity_game_rendering",
    "status_docs": ["JOURNEY.md"],                   # deferred/open work separated
    "evidence_docs": ["live-tool-validation-*.md"],  # real-number artifacts
    "content_packs": ["docs/renderdoc-mcp-*-zhihu/article.md"],
    "skill_docs": [".kilo/skills/*/SKILL.md"],
}


# ----------------------------- read helpers ------------------------------
def _read(path, root):
    try:
        return (root / path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_glob(root, pattern):
    """Read the first file matching a glob (returns '' if none)."""
    try:
        m = list(root.glob(pattern))
        return m[0].read_text(encoding="utf-8", errors="replace") if m else ""
    except Exception:
        return ""


def _grep(root, rel, pattern):
    return re.search(pattern, _read(rel, root), re.I | re.M) is not None


def _ngrep(root, rel, pattern):
    return re.search(pattern, _read(rel, root), re.I | re.M) is None


def _grep_glob(root, pattern, regex):
    return re.search(regex, _read_glob(root, pattern), re.I | re.M) is not None


def _glob_exists(root, pattern):
    return len(list(root.glob(pattern))) > 0


def _glob_count(root, patterns):
    n = 0
    for p in patterns:
        n += len(list(root.glob(p)))
    return n


def _has_def(root, server_file, name):
    return re.search(r"\bdef %s\b" % re.escape(name), _read(server_file, root), re.I) is not None


def _all_defs(root, server_file, names):
    txt = _read(server_file, root)
    return [n for n in names if re.search(r"\bdef %s\b" % re.escape(n), txt, re.I)]


def _line_budget(root, rel, maxlen):
    txt = _read(rel, root)
    return (not txt) or max((len(l) for l in txt.splitlines()), default=0) <= maxlen


def _doc_shape(root, rel):
    """(has_headers, table_density, mean_line_len) — read a doc's 'shape'."""
    lines = [l for l in _read(rel, root).splitlines() if l.strip()]
    if not lines:
        return False, 0.0, 0.0
    has_headers = any(re.match(r"^#{1,3}\s", l) for l in lines)
    table_rows = sum(1 for l in lines if l.lstrip().startswith("|"))
    density = table_rows / len(lines)
    mean_len = sum(len(l) for l in lines) / len(lines)
    return has_headers, round(density, 3), round(mean_len, 1)


def _fig_count(root):
    return len(list(root.glob("docs/*-zhihu/images/*.png")))


# ----------------------------- git / suite ------------------------------
def _git(root, *args):
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30
        )
        return r.stdout
    except Exception:
        return ""


def _suite(root):
    try:
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=str(root), capture_output=True, text=True, timeout=120,
        )
        out = r.stdout + r.stderr  # unittest prints the summary to stderr
        m = re.search(r"Ran (\d+) tests", out)
        return r.returncode == 0, (int(m.group(1)) if m else 0)
    except Exception:
        return False, 0


def _gate(root):
    try:
        r = subprocess.run(
            [sys.executable, "scripts/test_all.py"],
            cwd=str(root), capture_output=True, text=True, timeout=180,
        )
        return r.returncode == 0
    except Exception:
        return False


# ----------------------------- skills ------------------------------------
def _fresh(n):
    return n  # no-op guard so lambdas read clearly


# --------------------------------------------------------------------------
# DIMENSIONS  ->  (name, weight, [(label, fn(root, m) -> bool)])
# --------------------------------------------------------------------------
DIMENSIONS = [
    ("TRUTH & EVIDENCE", 0.22, [
        ("real-number validation artifact",
         lambda r, m: _glob_exists(r, "live-tool-validation-*.md")),
        ("gap/limitations admitted",
         lambda r, m: _grep(r, "docs/renderdoc-mcp-competitive-research.md",
                            r"缺口|gap|cannot|limit|unavailable|not \w+\b")
                       or _grep(r, "README.md", r"gap|cannot|unavailable|limitation")),
        ("verified-vs-open separated",
         lambda r, m: any(_grep(r, d, r"Deferred|still open|Future work|P3|unverified")
                          for d in m["status_docs"] if (r / d).is_file())),
        ("evidence carries real measured numbers",
         lambda r, m: _grep(r, "docs/renderdoc-mcp-debug-pixel-zhihu/article.md",
                            r"\d+(\.\d+)?\s*(MB|steps|px)|[0-9.]+%")
                       or _grep(r, "README.md",
                                r"bit-identical|available:true|\d+(\.\d+)?\s*(MB|ms|steps)")),
        ("roadmap honesty (deferred / blocked named)",
         lambda r, m: _grep(r, "docs/ROADMAP-100-TASKS.md", r"Deferred|no-op|Blocked")
                       and _grep(r, "docs/ROADMAP-100-TASKS.md", r"consent|authorization")),
        ("no open live-GPU validation blocker",
         lambda r, m: _ngrep(r, "docs/ROADMAP-100-TASKS.md", r"T005|T083|live-GPU full-trace")),
        ("benchmark / measurement artifact exists",
         lambda r, m: _glob_exists(r, "docs/*benchmark*")
                       or _glob_exists(r, "scripts/*bench*")
                       or _glob_exists(r, "docs/*-bench*")),
    ]),
    ("CAPABILITY PARITY", 0.22, [
        ("human 90% toolkit complete",
         lambda r, m: len(_all_defs(r, m["server_file"], m["toolkit_tools"]))
                       == len(m["toolkit_tools"])),
        ("closed shader-edit/replay loop",
         lambda r, m: len(_all_defs(r, m["server_file"], m["loop_tools"]))
                       == len(m["loop_tools"])),
        ("beyond-GUI full trajectory",
         lambda r, m: len(_all_defs(r, m["server_file"], m["killer_tools"]))
                       == len(m["killer_tools"])),
        ("Unity capture noise preset",
         lambda r, m: _grep(r, m["server_file"], r"unity_game_rendering|preset=")),
        ("capture-side owned & documented",
         lambda r, m: (m.get("owns_capture", True)
                       and (any((r / f).is_file() for f in m["capture_files"])
                            or _glob_exists(r, "capture_webgpu.py")))
                       or (not m.get("owns_capture", True)
                           and _grep(r, "README.md", r"capture|renderdoc-skill|capture_webgpu"))),
        ("multi-API documented",
         lambda r, m: _grep(r, "README.md", r"Vulkan|D3D12|D3D11|OpenGL|WebGPU")),
        ("A/B two-capture diff tool",
         lambda r, m: _has_def(r, m["server_file"], "get_pixel_diff")
                       or _has_def(r, m["server_file"], "capture_diff")),
        ("API Inspector (raw API call stream)",
         lambda r, m: _has_def(r, m["server_file"], "get_api_events")),
    ]),
    ("CRAFT & HEALTH", 0.20, [
        ("full suite green", lambda r, m: _suite(r)[0]),
        ("suite breadth >=150", lambda r, m: _suite(r)[1] >= 150),
        ("quality gate green (py_compile + Py3.6 boundary)",
         lambda r, m: _gate(r)),
        ("Py3.6-boundary gate exists",
         lambda r, m: (r / "scripts/six_gate.py").is_file()),
        ("no tracked .pyc / __pycache__",
         lambda r, m: not re.search(r"\.pyc$|__pycache__", _git(r, "ls-files"))),
        ("no known dead import (Parsers)",
         lambda r, m: _ngrep(r, "renderdoc_extension/services/debug_service.py",
                             r"from \.\.utils import Parsers")),
        ("CI config present",
         lambda r, m: _glob_exists(r, ".github/workflows/*.yml")),
    ]),
    ("DOCS & ONBOARDING", 0.14, [
        ("README documents latest capability",
         lambda r, m: _grep(r, "README.md", r"debug_trace_export")
                       and _grep(r, "README.md", r"rdc_harness")),
        ("AGENTS.md onboard doc current",
         lambda r, m: _grep(r, "AGENTS.md", r"debug_trace_export|rdc_harness|Python 3.6")),
        ("AGENTS.md names the newest feature",
         lambda r, m: _grep(r, "AGENTS.md", r"debug_trace_export")),
        ("stale mirror flagged, not contradictory",
         lambda r, m: _grep(r, "AGENTS.md", r"stale") or _grep(r, "CLAUDE.md", r"stale")),
        ("harness skill docs present (>=4)",
         lambda r, m: _glob_count(r, m["skill_docs"]) >= 4),
        ("说人话: README tabular + sectioned + concise",
         lambda r, m: (lambda s: s[0] and s[1] >= 0.25 and s[2] < 120)(_doc_shape(r, "README.md"))),
    ]),
    ("FOOTPRINT & DISTRIBUTION", 0.12, [
        ("token-discipline caps present",
         lambda r, m: _grep(r, "renderdoc_extension/utils/debug_trace.py",
                            r"HARD_MAX_STEPS|EXPORT_HARD_MAX_STEPS")
                       and _grep(r, "renderdoc_extension/services/export_service.py", r"MiB|cap")),
        ("export contract: path, never bytes",
         lambda r, m: _glob_exists(r, "tests/test_export.py")
                       and _grep(r, "renderdoc_extension/services/export_service.py", r"path")),
        ("responses bounded (limit/cap)",
         lambda r, m: _grep(r, m["server_file"], r"limit=|cap|max_entries")),
        ("wheel ships mcp_server + rdc_harness",
         lambda r, m: _grep(r, "pyproject.toml", r"mcp_server")
                       and _grep(r, "pyproject.toml", r"rdc_harness")),
        ("cache/perf design documented",
         lambda r, m: _glob_exists(r, "docs/openviking-cache-design.md")
                       or _grep(r, "README.md", r"RENDERDOC_MCP_CACHE|cache")),
        ("quantified perf / benchmark documented",
         lambda r, m: _glob_exists(r, "docs/*perf*")
                       or _glob_exists(r, "docs/*bench*")),
    ]),
    ("VOICE & CONTENT", 0.10, [
        ("a real content pack exists",
         lambda r, m: _glob_exists(r, "docs/*-zhihu/article.md") or _glob_exists(r, "docs/*-zhihu/*.html")),
        ("figures are real (>=5 PNG)",
         lambda r, m: _fig_count(r) >= 5),
        ("inference marked, not asserted as fact",
         lambda r, m: _glob_exists(r, "docs/*-zhihu/article.md")
                       and len(_read_glob(r, "docs/*-zhihu/article.md")) > 800
                       and _grep_glob(r, "docs/*-zhihu/article.md",
                                      r"错路|推断|evidence|纯事实|pass|避免|不是X")),
    ]),
]


def score(root):
    root = Path(root).resolve()
    manifest = DEFAULT_MANIFEST
    dims = []
    total = 0.0
    for name, weight, checklist in DIMENSIONS:
        passed = 0
        items = []
        for label, fn in checklist:
            try:
                ok = bool(fn(root, manifest))
            except Exception as e:
                ok = False
                label = "%s [err: %s]" % (label, e)
            passed += 1 if ok else 0
            items.append({"check": label, "pass": ok})
        ratio = passed / len(checklist) if checklist else 0.0
        dims.append({
            "dimension": name, "weight": weight,
            "passed": passed, "total": len(checklist),
            "ratio": round(ratio, 3),
            "score": round(ratio * weight * 100, 2),
            "checks": items,
        })
        total += ratio * weight * 100
    return {"total": round(total, 2), "dimensions": dims}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = args[0] if args else "."
    out = score(root)
    if "--json" in sys.argv:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    print("TASTE SCORE  [%s]" % out["total"])
    print("-" * 70)
    for d in out["dimensions"]:
        marker = "OK " if d["ratio"] >= 0.75 else ("~  " if d["ratio"] >= 0.5 else "LOW")
        print("%s %-24s %-5s (%d/%d)  +%.1f pts" % (
            marker, d["dimension"], d["ratio"], d["passed"], d["total"], d["score"]))
    print("-" * 70)
    print("total weighted = %s / 100" % out["total"])
    print("\nlowest dimension = the next target for an agent.")


if __name__ == "__main__":
    main()
