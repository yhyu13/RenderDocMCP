"""RenderDoc verification & fix harness.

Closes the gap identified across the three design documents:
    - interview guide        -> token funnel, MCP-vs-Skill split, anomaly rules
    - token-efficient guide  -> Layer1/Layer2 summaries + auto_red_flags
    - perception-agent doc   -> L1 deterministic + L2 behavioral verification,
                                shader edit/replay orchestrator, fix report

This package is RenderDoc-agnostic: every rule, check, and the loop operate
on plain dicts/bytes so they run without a GPU and can be backed later by
the MCP bridge or the RenderDoc controller API.

Process placement: this package runs on the **AI/MCP side** of the hybrid
process split (standard Python >= 3.10). Do NOT import it from inside
``renderdoc_extension/``, which runs RenderDoc's embedded Python 3.6
(stdlib-only) and would fail to parse these annotations.

Run tests: ``python -m unittest discover -s tests``.
"""

from .models import (
    Anomaly,
    CheckResult,
    CheckStatus,
    Severity,
    VerificationReport,
)
from .rules import (
    Thresholds,
    check_invisible_pipeline,
    detect_red_flags,
    run_deterministic,
)
from .behavioral import (
    BehavioralThresholds,
    PixelDiff,
    pixel_diff,
    psnr,
    rt_hash,
    run_behavioral,
    score_from_report,
    threshold_verdict,
)
from .summarize import (
    build_frame_summary,
    build_pass_summary,
    compact_frame,
    estimate_tokens,
)
from .orchestrator import (
    ShaderBackend,
    ShaderCompileError,
    ShaderPatcher,
    iterate_shader_fix,
)
from .renderdoc_backend import RenderDocShaderBackend
from .report import build_fix_report, render_markdown
from .export import (
    artifacts_from_fix_report,
    check_against_golden,
    load_golden,
    shader_unified_diff,
    write_golden,
    write_shader_patch,
)
from .human_toolkit import (
    UNITY_EXCLUDE_MARKERS,
    UNITY_GAME_RENDERING_PRESET,
    cap_history,
    decode_position_vertices,
    resolve_draw_filters,
    serialize_pixel_modification,
)

__all__ = [
    "Anomaly",
    "CheckResult",
    "CheckStatus",
    "Severity",
    "VerificationReport",
    "Thresholds",
    "detect_red_flags",
    "run_deterministic",
    "check_invisible_pipeline",
    "UNITY_EXCLUDE_MARKERS",
    "UNITY_GAME_RENDERING_PRESET",
    "cap_history",
    "decode_position_vertices",
    "resolve_draw_filters",
    "serialize_pixel_modification",
    "BehavioralThresholds",
    "PixelDiff",
    "pixel_diff",
    "psnr",
    "rt_hash",
    "run_behavioral",
    "score_from_report",
    "threshold_verdict",
    "build_frame_summary",
    "build_pass_summary",
    "compact_frame",
    "estimate_tokens",
    "ShaderBackend",
    "ShaderCompileError",
    "ShaderPatcher",
    "iterate_shader_fix",
    "RenderDocShaderBackend",
    "build_fix_report",
    "render_markdown",
    "artifacts_from_fix_report",
    "check_against_golden",
    "load_golden",
    "shader_unified_diff",
    "write_golden",
    "write_shader_patch",
]
