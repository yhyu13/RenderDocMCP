"""L1 deterministic verification + auto-red-flag rule engine.

This is the "zero model cost" layer (perception-agent design doc §3.1):
pure functions over structured JSON, no RenderDoc/GPU/LLM required.

Sources of truth for thresholds:
    - token-efficient guide §10.2 (anomaly detection table)
    - interview guide §2.2 (SetPass burst, RT switching, oversized textures)
    - perception-agent design doc §3.1 (numeric constraints, binding completeness)
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Optional

from .models import Anomaly, CheckResult, CheckStatus, Severity, VerificationReport

# Formats that are compressed (block-compressed / ASTC / ETC). Anything else
# is treated as "uncompressed" and flagged as a low-severity waste signal.
COMPRESSED_FORMAT_HINTS = (
    "BC1", "BC2", "BC3", "BC4", "BC5", "BC6H", "BC7",
    "ASTC", "ETC1", "ETC2", "EAC", "DXT", "PVRTC",
)


@dataclass
class Thresholds:
    """Tunable thresholds for all rules. Mirrors the doc tables."""

    ps_ratio_pct: float = 50.0          # PS 耗时占比 > 50% -> Pixel-bound
    single_pass_ms: float = 5.0         # 单 Pass > 5ms
    draw_call_count: int = 3000         # Draw Call > 3000
    overdraw_ratio: float = 8.0         # Overdraw > 8x
    ui_pass_ms: float = 2.0             # UI Pass > 2ms
    bandwidth_pct: float = 80.0         # L2/DRAM 带宽 > 80%
    batching_same_mesh: int = 10        # 同一 Mesh 多次 Draw 未合批 >= 10
    oversized_texture_px: int = 4096 * 4096  # 单纹理像素数超限 (interview §2.2)
    setpass_count: int = 200            # SetPass burst (interview §2.2)
    rt_switch_count: int = 50           # RT 切换次数 (interview §2.2)

    def with_overrides(self, **kw: Any) -> "Thresholds":
        return replace(self, **kw)


def _num(value: Any) -> Optional[float]:
    """Coerce to float, returning None when unusable."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _get(mapping: Optional[Mapping[str, Any]], *keys: str) -> Any:
    """Safe nested-ish lookup: returns first key present, else None."""
    if not mapping:
        return None
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _result(rule: str, severity: Severity, ok: bool, message: str,
            expected: Any, actual: Any, evidence: Optional[dict] = None,
            status: Optional[CheckStatus] = None) -> CheckResult:
    if status is None:
        status = CheckStatus.PASS if ok else CheckStatus.FAIL
    return CheckResult(
        rule=rule, status=status, severity=severity, message=message,
        expected=expected, actual=actual, evidence=evidence or {},
    )


# ---------------------------------------------------------------------------
# Individual rules (each: (Thresholds, ctx) -> CheckResult | None)
# ---------------------------------------------------------------------------

def rule_fps_budget(t: Thresholds, frame: Mapping[str, Any]) -> Optional[CheckResult]:
    total = _num(_get(frame, "total_gpu_ms"))
    target = _num(_get(frame, "fps_target_ms"))
    if total is None or target is None:
        return None
    over = total > target
    return _result(
        "fps_budget", Severity.HIGH, not over,
        "frame over GPU budget" if over else "frame within GPU budget",
        expected=f"<= {target} ms", actual=total,
        evidence={"over_by_ms": round(total - target, 3)},
    )


def rule_bottleneck(t: Thresholds, frame: Mapping[str, Any]) -> Optional[CheckResult]:
    stage = _get(frame, "gpu_stage_breakdown_ms")
    if not isinstance(stage, Mapping):
        return None
    total = sum(v for v in stage.values() if isinstance(v, (int, float))) or 0.0
    ps = _num(stage.get("pixel_shader"))
    if total <= 0 or ps is None:
        return None
    ratio = ps / total * 100.0
    pixel_bound = ratio > t.ps_ratio_pct
    return _result(
        "bottleneck", Severity.HIGH, not pixel_bound,
        "pixel-bound (PS dominates)" if pixel_bound else "not pixel-bound",
        expected=f"PS <= {t.ps_ratio_pct}%", actual=f"{ratio:.1f}%",
        evidence={"ps_ratio_pct": round(ratio, 2)},
    )


def rule_draw_count(t: Thresholds, frame: Mapping[str, Any]) -> Optional[CheckResult]:
    stats = _get(frame, "api_stats")
    if not isinstance(stats, Mapping):
        return None
    draws = _num(stats.get("draw_calls"))
    if draws is None:
        return None
    return _result(
        "draw_count", Severity.MEDIUM, draws <= t.draw_call_count,
        "draw call count above threshold" if draws > t.draw_call_count else "draw count ok",
        expected=f"<= {t.draw_call_count}", actual=int(draws),
    )


def rule_single_pass(t: Thresholds, frame: Mapping[str, Any]) -> Optional[CheckResult]:
    passes = _get(frame, "top_passes_by_ms")
    if not isinstance(passes, list):
        return None
    worst = None
    for p in passes:
        if not isinstance(p, Mapping):
            continue
        ms = _num(p.get("ms"))
        if ms is not None and (worst is None or ms > worst["ms"]):
            worst = {"name": p.get("name", "?"), "ms": ms}
    if worst is None:
        return None
    return _result(
        "single_pass", Severity.MEDIUM, worst["ms"] <= t.single_pass_ms,
        "single pass exceeds time budget" if worst["ms"] > t.single_pass_ms else "passes within budget",
        expected=f"<= {t.single_pass_ms} ms", actual=worst["ms"],
        evidence={"pass": worst["name"]},
    )


def rule_overdraw(t: Thresholds, frame: Mapping[str, Any]) -> Optional[CheckResult]:
    od = _num(_get(frame, "overdraw_estimate"))
    if od is None:
        return None
    return _result(
        "overdraw", Severity.MEDIUM, od <= t.overdraw_ratio,
        "overdraw above threshold" if od > t.overdraw_ratio else "overdraw ok",
        expected=f"<= {t.overdraw_ratio}x", actual=od,
    )


def rule_ui_pass(t: Thresholds, frame: Mapping[str, Any]) -> Optional[CheckResult]:
    passes = _get(frame, "top_passes_by_ms")
    if not isinstance(passes, list):
        return None
    for p in passes:
        if not isinstance(p, Mapping):
            continue
        name = str(p.get("name", ""))
        if "UI" in name.upper():
            ms = _num(p.get("ms"))
            if ms is None:
                return None
            return _result(
                "ui_pass", Severity.MEDIUM, ms <= t.ui_pass_ms,
                "UI pass over budget (check UI rebuild)" if ms > t.ui_pass_ms else "UI pass ok",
                expected=f"<= {t.ui_pass_ms} ms", actual=ms, evidence={"pass": name},
            )
    return None


def rule_bandwidth(t: Thresholds, frame: Mapping[str, Any]) -> Optional[CheckResult]:
    mem = _get(frame, "memory_bandwidth")
    if not isinstance(mem, Mapping):
        return None
    pct = _num(mem.get("l2_throughput_pct"))
    status = mem.get("bandwidth_status")
    if status == "saturated":
        return _result("bandwidth", Severity.HIGH, False,
                       "memory bandwidth saturated", expected="healthy", actual=status)
    if pct is not None and pct > t.bandwidth_pct:
        return _result("bandwidth", Severity.HIGH, False,
                       "bandwidth throughput above threshold",
                       expected=f"<= {t.bandwidth_pct}%", actual=pct)
    if pct is None and not status:
        # No throughput signal and no status -> not verifiable, not a pass.
        return None
    return _result("bandwidth", Severity.MEDIUM, True, "bandwidth healthy",
                   expected=f"<= {t.bandwidth_pct}%",
                   actual=pct if pct is not None else status)


def rule_batching(t: Thresholds, frame: Mapping[str, Any]) -> Optional[CheckResult]:
    bi = _get(frame, "batching_issues")
    if not isinstance(bi, Mapping):
        return None
    same_mesh = _num(bi.get("same_mesh_different_pso"))
    if same_mesh is None:
        return None
    return _result(
        "batching", Severity.MEDIUM, same_mesh < t.batching_same_mesh,
        "batching opportunity (same mesh, different PSO)" if same_mesh >= t.batching_same_mesh else "batching ok",
        expected=f"< {t.batching_same_mesh}", actual=int(same_mesh),
    )


def rule_textures(t: Thresholds, frame: Mapping[str, Any]) -> list[CheckResult]:
    """Oversized / uncompressed / unmipped texture checks (interview §2.2, doc2 §5.2)."""
    resources = _get(frame, "top_resources")
    textures = None
    if isinstance(resources, Mapping):
        textures = resources.get("textures") or resources.get("largest_textures")
    if not isinstance(textures, list):
        return []

    results: list[CheckResult] = []
    oversized = 0
    uncompressed = 0
    unmipped = 0
    for tex in textures:
        if isinstance(tex, str):
            # Names only; can't verify size/format — record presence only.
            continue
        if not isinstance(tex, Mapping):
            continue
        w = _num(tex.get("width"))
        h = _num(tex.get("height"))
        if w is not None and h is not None and w * h > t.oversized_texture_px:
            oversized += 1
        fmt = str(tex.get("format", ""))
        if fmt and not any(hint in fmt.upper() for hint in COMPRESSED_FORMAT_HINTS):
            uncompressed += 1
        mips = _num(tex.get("mip_levels"))
        if mips is not None and mips <= 1:
            unmipped += 1

    results.append(_result(
        "oversized_texture", Severity.HIGH, oversized == 0,
        "oversized texture(s) present" if oversized else "texture sizes ok",
        expected="0", actual=oversized, evidence={"count": oversized},
    ))
    results.append(_result(
        "uncompressed_texture", Severity.LOW, uncompressed == 0,
        "uncompressed texture(s) present" if uncompressed else "textures compressed",
        expected="0", actual=uncompressed, evidence={"count": uncompressed},
    ))
    results.append(_result(
        "unmipped_texture", Severity.LOW, unmipped == 0,
        "unmipped texture(s) present" if unmipped else "mip chains present",
        expected="0", actual=unmipped, evidence={"count": unmipped},
    ))
    return results


def rule_setpass_rt(t: Thresholds, frame: Mapping[str, Any]) -> list[CheckResult]:
    """SetPass burst / RT switching anomalies (interview §2.2)."""
    stats = _get(frame, "api_stats")
    if not isinstance(stats, Mapping):
        return []
    results: list[CheckResult] = []
    setpass = _num(stats.get("state_changes"))  # proxy for SetPass
    if setpass is not None:
        results.append(_result(
            "setpass_burst", Severity.HIGH, setpass <= t.setpass_count,
            "SetPass burst (too many state changes)" if setpass > t.setpass_count else "SetPass ok",
            expected=f"<= {t.setpass_count}", actual=int(setpass),
        ))
    rt = _num(stats.get("rt_switches"))
    if rt is not None:
        results.append(_result(
            "rt_switching", Severity.MEDIUM, rt <= t.rt_switch_count,
            "excessive render target switching" if rt > t.rt_switch_count else "RT switching ok",
            expected=f"<= {t.rt_switch_count}", actual=int(rt),
        ))
    return results


# ---------------------------------------------------------------------------
# Numeric constraint + binding completeness (perception doc §3.1)
# ---------------------------------------------------------------------------

def check_min_lod(pass_summary: Mapping[str, Any]) -> Optional[CheckResult]:
    """minLod must not exceed mip count (numeric constraint, doc3 §3.1)."""
    sampler = _get(pass_summary, "samplers")
    if not isinstance(sampler, list) or not sampler:
        # No samplers to check -> not verifiable, not a pass.
        return None
    checked = False
    for s in sampler:
        if not isinstance(s, Mapping):
            continue
        min_lod = _num(s.get("min_lod"))
        mip_count = _num(s.get("mip_levels"))
        if min_lod is None or mip_count is None:
            continue
        checked = True
        if min_lod > mip_count:
            return _result(
                "min_lod", Severity.MEDIUM, False,
                "minLod exceeds mip count",
                expected=f"minLod <= {mip_count}", actual=min_lod,
                evidence={"slot": s.get("slot"), "name": s.get("name")},
            )
    if not checked:
        # Samplers present but none carried a checkable minLod -> no signal.
        return None
    return _result("min_lod", Severity.MEDIUM, True, "minLod constraints satisfied",
                   expected="minLod <= mip count", actual="ok")


def check_validation_messages(
    messages: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Optional[CheckResult]:
    """Validation-layer messages must be empty of error/high severity (doc3 §3.1)."""
    if not messages:
        return None
    errors = [
        m for m in messages
        if isinstance(m, Mapping)
        and str(m.get("severity", "")).lower() in ("error", "high")
    ]
    if errors:
        return _result(
            "validation_messages", Severity.HIGH, False,
            "%d validation error(s) in last replay" % len(errors),
            expected="0 errors", actual=len(errors),
            evidence={"messages": errors[:10]},
        )
    return _result(
        "validation_messages", Severity.HIGH, True,
        "no validation errors", expected="0 errors", actual=0,
    )


def check_binding_completeness(pipeline: Mapping[str, Any]) -> Optional[CheckResult]:
    """Resource binding completeness (doc3 §3.1): bound shader must have its inputs bound."""
    shaders = _get(pipeline, "shaders")
    if not isinstance(shaders, Mapping) or not shaders:
        return None
    missing: list[dict[str, Any]] = []
    for stage, info in shaders.items():
        if not isinstance(info, Mapping):
            continue
        resources = info.get("resources")
        if resources is not None and not resources:
            missing.append({"stage": stage, "reason": "no resources bound"})
    if missing:
        return _result(
            "binding_completeness", Severity.HIGH, False,
            "shader stage(s) with no resource bindings",
            expected="each shader stage has bindings", actual=missing,
        )
    return _result("binding_completeness", Severity.HIGH, True,
                   "all shader stages have bindings", expected="ok", actual="ok")


# ---------------------------------------------------------------------------
# Engine entry points
# ---------------------------------------------------------------------------

def detect_red_flags(
    frame: Mapping[str, Any],
    thresholds: Optional[Thresholds] = None,
) -> list[Anomaly]:
    """Run all anomaly rules and return the failures as Anomaly objects.

    This is the token-efficient guide §10.2 "auto_red_flags": the script
    pre-computes the obvious problems so the LLM never has to re-derive them.
    """
    t = thresholds or Thresholds()
    report = run_deterministic(frame, thresholds=t)
    return [
        Anomaly(rule=c.rule, severity=c.severity, message=c.message, evidence=c.evidence)
        for c in report.checks
        if c.status is CheckStatus.FAIL
    ]


_FRAME_RULES = (
    ("fps_budget", rule_fps_budget),
    ("bottleneck", rule_bottleneck),
    ("draw_count", rule_draw_count),
    ("single_pass", rule_single_pass),
    ("overdraw", rule_overdraw),
    ("ui_pass", rule_ui_pass),
    ("bandwidth", rule_bandwidth),
    ("batching", rule_batching),
)


def _skip(rule_name: str) -> CheckResult:
    """Emit a SKIP check for a rule whose required data was absent."""
    return CheckResult(
        rule=rule_name, status=CheckStatus.SKIP, severity=Severity.LOW,
        message=f"no data for rule '{rule_name}'",
    )


def run_deterministic(
    frame: Mapping[str, Any],
    passes: Optional[Iterable[Mapping[str, Any]]] = None,
    pipeline: Optional[Mapping[str, Any]] = None,
    thresholds: Optional[Thresholds] = None,
    debug_messages: Optional[Iterable[Mapping[str, Any]]] = None,
) -> VerificationReport:
    """Run the full L1 deterministic verification layer.

    Frame-level rules whose required data is absent are emitted as SKIP, so
    the report degrades to "nothing verified" (``all_pass()`` is False)
    instead of a false pass. Auxiliary anomaly rules (textures, setpass/RT,
    minLod, binding, validation messages) are omitted when their inputs are
    not supplied.
    """
    t = thresholds or Thresholds()
    checks: list[CheckResult] = []

    for name, rule in _FRAME_RULES:
        result = rule(t, frame)
        checks.append(result if result is not None else _skip(name))

    checks.extend(rule_textures(t, frame))
    checks.extend(rule_setpass_rt(t, frame))

    for ps in passes or ():
        result = check_min_lod(ps)
        if result is not None:
            checks.append(result)

    if pipeline is not None:
        result = check_binding_completeness(pipeline)
        if result is not None:
            checks.append(result)

    result = check_validation_messages(debug_messages)
    if result is not None:
        checks.append(result)

    return VerificationReport(layer="L1", checks=checks)
