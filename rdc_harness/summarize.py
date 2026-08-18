"""Layer 1 / Layer 2 summary builders + token-compact formatter.

Implements the token-efficient guide §3 (frame-level) and §4 (pass-level),
plus the interview guide §2.3 "directory" compaction. These are pure
transforms: raw dicts in, structured dicts out, so the LLM only ever sees
already-aggregated, already-sorted data.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .rules import detect_red_flags, Thresholds


def build_frame_summary(
    *,
    total_gpu_ms: float | None = None,
    total_cpu_ms: float | None = None,
    fps_target_ms: float | None = None,
    api_stats: Mapping[str, Any] | None = None,
    gpu_stage_breakdown_ms: Mapping[str, float] | None = None,
    memory_bandwidth: Mapping[str, Any] | None = None,
    top_passes_by_ms: Sequence[Mapping[str, Any]] | None = None,
    top_resources: Mapping[str, Any] | None = None,
    overdraw_estimate: float | None = None,
    batching_issues: Mapping[str, Any] | None = None,
    thresholds: Thresholds | None = None,
) -> dict[str, Any]:
    """Assemble the Doc2 §3 Layer-1 JSON, adding auto_red_flags.

    ``auto_red_flags`` is computed locally by :func:`rdc_harness.rules.detect_red_flags`
    so the statistics are pre-judged by the script, not left to the model.
    """
    frame: dict[str, Any] = {}
    if total_gpu_ms is not None:
        frame["total_gpu_ms"] = total_gpu_ms
    if total_cpu_ms is not None:
        frame["total_cpu_ms"] = total_cpu_ms
    if fps_target_ms is not None:
        frame["fps_target_ms"] = fps_target_ms

    if api_stats is not None:
        frame["api_stats"] = dict(api_stats)
    if gpu_stage_breakdown_ms is not None:
        frame["gpu_stage_breakdown_ms"] = dict(gpu_stage_breakdown_ms)
    if memory_bandwidth is not None:
        frame["memory_bandwidth"] = dict(memory_bandwidth)
    if top_passes_by_ms is not None:
        frame["top_passes_by_ms"] = list(top_passes_by_ms)
    if top_resources is not None:
        frame["top_resources"] = dict(top_resources)
    if overdraw_estimate is not None:
        frame["overdraw_estimate"] = overdraw_estimate
    if batching_issues is not None:
        frame["batching_issues"] = dict(batching_issues)

    frame["auto_red_flags"] = [
        a.to_dict() for a in detect_red_flags(frame, thresholds=thresholds)
    ]
    return frame


def build_pass_summary(
    *,
    name: str,
    total_ms: float | None = None,
    draw_count: int | None = None,
    stage_breakdown_ms: Mapping[str, float] | None = None,
    top_draws_by_ms: Sequence[Mapping[str, Any]] | None = None,
    psos_in_pass: Mapping[str, Any] | None = None,
    batching_issues: Mapping[str, Any] | None = None,
    overdraw_estimate: float | None = None,
    render_targets: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Assemble the Doc2 §4 Layer-2 pass summary."""
    summary: dict[str, Any] = {"pass": name}
    if total_ms is not None:
        summary["total_ms"] = total_ms
    if draw_count is not None:
        summary["draw_count"] = draw_count
    if stage_breakdown_ms is not None:
        summary["stage_breakdown_ms"] = dict(stage_breakdown_ms)
    if top_draws_by_ms is not None:
        summary["top_draws_by_ms"] = list(top_draws_by_ms)
    if psos_in_pass is not None:
        summary["psos_in_pass"] = dict(psos_in_pass)
    if batching_issues is not None:
        summary["batching_issues"] = dict(batching_issues)
    if overdraw_estimate is not None:
        summary["overdraw_estimate"] = overdraw_estimate
    if render_targets is not None:
        summary["render_targets"] = list(render_targets)
    return summary


def compact_frame(frame: Mapping[str, Any]) -> str:
    """Render a frame summary as a terse "directory" (interview §2.3, < ~200 tokens)."""
    lines: list[str] = []
    total = frame.get("total_gpu_ms")
    draws = (frame.get("api_stats") or {}).get("draw_calls")
    header = []
    if total is not None:
        header.append(f"GPU {total}ms")
    if draws is not None:
        header.append(f"{draws} draws")
    lines.append("Frame: " + ", ".join(header))

    for p in frame.get("top_passes_by_ms") or []:
        verdict = p.get("verdict", "")
        lines.append(f"  - {p.get('name', '?')}: {p.get('ms', '?')}ms "
                     f"{p.get('draws', '?')} draws"
                     + (f" [{verdict}]" if verdict else ""))

    for flag in frame.get("auto_red_flags") or []:
        lines.append(f"  ! {flag.get('message', '')}")
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) for budget assertions in tests."""
    return max(1, len(text) // 4)
