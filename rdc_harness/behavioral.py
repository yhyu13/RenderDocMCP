"""L2 behavioral verification (perception-agent design doc §3.2).

Runs only after L1 passes (doc3 §3.3 ordering). Checks semantic regressions
that need pixel comparison: golden diff, render-target hash, PSNR, and
pixel-history overdraw evidence.

Pure Python with an optional numpy fast path for large images; falls back
to a byte loop when numpy is unavailable so the module always imports.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Optional

from .models import CheckResult, CheckStatus, Severity, VerificationReport
from .rules import _result  # canonical CheckResult constructor (single source of truth)

try:  # optional acceleration; not a hard dependency
    import numpy as _np
except ImportError:  # pragma: no cover - depends on environment
    _np = None


@dataclass
class PixelDiff:
    """Byte-wise difference between two same-length RGBA8 buffers."""

    total_pixels: int
    changed_pixels: int
    changed_fraction: float
    mean_abs_error: float
    max_abs_error: int

    def to_dict(self) -> dict:
        return {
            "total_pixels": self.total_pixels,
            "changed_pixels": self.changed_pixels,
            "changed_fraction": round(self.changed_fraction, 6),
            "mean_abs_error": round(self.mean_abs_error, 4),
            "max_abs_error": self.max_abs_error,
        }


@dataclass
class BehavioralThresholds:
    changed_fraction_warn: float = 0.01   # >1% changed -> warn
    changed_fraction_fail: float = 0.05   # >5% changed -> fail
    psnr_fail_db: float = 30.0            # PSNR below this -> fail
    overdraw_warn: int = 8                # draws touching a pixel -> warn


def rt_hash(data: bytes | bytearray | memoryview) -> str:
    """Deterministic render-target hash (doc3 §3.2: "关键事件 RT 哈希").

    Zero-copy: hashes through a memoryview so a full-res render target is not
    duplicated into a ``bytes`` buffer before hashing.
    """
    h = hashlib.sha256()
    h.update(memoryview(data))
    return h.hexdigest()


@dataclass
class _Stats:
    """Aggregated per-channel statistics from one pass over two buffers."""

    total_pixels: int
    changed_pixels: int
    sum_abs_error: int
    max_abs_error: int
    sum_sq_error: int
    n_channels: int


def _compute_stats(actual: bytes | bytearray | memoryview,
                   golden: bytes | bytearray | memoryview) -> _Stats:
    """Single pass producing every metric pixel_diff and psnr need.

    Uses numpy (int16 diff + int32 squares — never float64) when available so
    an 8K render target does not allocate multi-GB temporaries, and consumes
    the buffer protocol directly (no ``bytes()`` copy). Falls back to a
    byte loop otherwise.
    """
    n_actual = len(actual)
    n_golden = len(golden)
    if n_actual != n_golden:
        raise ValueError(f"buffer length mismatch: actual={n_actual} golden={n_golden}")
    if n_actual % 4 != 0:
        raise ValueError("buffer length must be a multiple of 4 (RGBA8)")

    total = n_actual // 4

    if _np is not None and total > 0:
        aa = _np.frombuffer(actual, dtype=_np.uint8).reshape(-1, 4)
        gg = _np.frombuffer(golden, dtype=_np.uint8).reshape(-1, 4)
        # Changed-pixel count from uint8 views (no subtraction/overflow).
        changed = int(_np.count_nonzero(_np.any(aa != gg, axis=1)))
        # One int16 diff feeds both the abs-error and squared-error metrics.
        d = aa.astype(_np.int16) - gg.astype(_np.int16)
        abs_d = _np.abs(d)
        sq = _np.square(d, dtype=_np.int32)
        return _Stats(
            total_pixels=total,
            changed_pixels=changed,
            sum_abs_error=int(abs_d.sum()),
            max_abs_error=int(abs_d.max()) if abs_d.size else 0,
            sum_sq_error=int(sq.sum()),
            n_channels=n_actual,
        )

    a = bytes(actual)
    g = bytes(golden)
    changed = 0
    sum_abs = 0
    max_abs = 0
    sum_sq = 0
    for i in range(0, n_actual, 4):
        if a[i:i + 4] != g[i:i + 4]:
            changed += 1
        for ca, cg in zip(a[i:i + 4], g[i:i + 4]):
            diff = ca - cg
            ad = abs(diff)
            sum_abs += ad
            sum_sq += diff * diff
            if ad > max_abs:
                max_abs = ad
    return _Stats(total, changed, sum_abs, max_abs, sum_sq, n_actual)


def pixel_diff(actual: bytes | bytearray | memoryview,
               golden: bytes | bytearray | memoryview) -> PixelDiff:
    """Compare two equal-length RGBA8 buffers bytewise."""
    s = _compute_stats(actual, golden)
    return PixelDiff(
        total_pixels=s.total_pixels,
        changed_pixels=s.changed_pixels,
        changed_fraction=(s.changed_pixels / s.total_pixels) if s.total_pixels else 0.0,
        mean_abs_error=(s.sum_abs_error / s.n_channels) if s.n_channels else 0.0,
        max_abs_error=s.max_abs_error,
    )


def psnr(actual: bytes | bytearray | memoryview,
         golden: bytes | bytearray | memoryview) -> float:
    """Peak signal-to-noise ratio in dB (byte-domain, peak=255)."""
    s = _compute_stats(actual, golden)
    if s.n_channels == 0:
        return float("inf")
    mse = s.sum_sq_error / s.n_channels
    if mse == 0:
        return float("inf")
    return 20.0 * math.log10(255.0) - 10.0 * math.log10(mse)


def run_behavioral(
    actual: bytes | bytearray | memoryview,
    golden: bytes | bytearray | memoryview,
    expected_hash: Optional[str] = None,
    pixel_history_draw_count: Optional[int] = None,
    thresholds: Optional[BehavioralThresholds] = None,
) -> VerificationReport:
    """Run the L2 behavioral layer against a golden image.

    Args:
        actual: The replayed render-target bytes.
        golden: The reference (golden) render-target bytes.
        expected_hash: Optional sha256 of the golden; when provided and the
            actual hash differs, this is a hard FAIL before pixel diff.
        pixel_history_draw_count: Optional number of draws that wrote a pixel
            (overdraw evidence from PickPixel/pixel history).
        thresholds: Tunable tolerances.
    """
    t = thresholds or BehavioralThresholds()
    checks: list[CheckResult] = []

    actual_hash = rt_hash(actual)
    if expected_hash is not None:
        match = actual_hash == expected_hash
        checks.append(_result(
            "rt_hash", Severity.HIGH, match,
            "render target hash matches golden" if match else "render target hash mismatch",
            expected=expected_hash, actual=actual_hash,
        ))
        if not match:
            # Known-bad capture: the golden hash already proves inequality, so
            # skip the (potentially expensive) pixel diff / PSNR scan entirely.
            return VerificationReport(layer="L2", checks=checks)

    # One pass over the buffers feeds both the pixel-diff and PSNR checks.
    stats = _compute_stats(actual, golden)
    changed_fraction = (stats.changed_pixels / stats.total_pixels) if stats.total_pixels else 0.0
    mean_abs = (stats.sum_abs_error / stats.n_channels) if stats.n_channels else 0.0

    if changed_fraction > t.changed_fraction_fail:
        status, sev = CheckStatus.FAIL, Severity.HIGH
    elif changed_fraction > t.changed_fraction_warn:
        status, sev = CheckStatus.WARN, Severity.MEDIUM
    else:
        status, sev = CheckStatus.PASS, Severity.MEDIUM
    checks.append(_result(
        "pixel_diff", sev, status is not CheckStatus.FAIL,
        f"pixel difference {changed_fraction:.4%}",
        expected=f"<= {t.changed_fraction_warn:.2%}", actual=changed_fraction,
        evidence={
            "total_pixels": stats.total_pixels,
            "changed_pixels": stats.changed_pixels,
            "changed_fraction": round(changed_fraction, 6),
            "mean_abs_error": round(mean_abs, 4),
            "max_abs_error": stats.max_abs_error,
        },
        status=status,
    ))

    if stats.n_channels > 0:
        mse = stats.sum_sq_error / stats.n_channels
        if mse > 0:
            p = 20.0 * math.log10(255.0) - 10.0 * math.log10(mse)
            checks.append(_result(
                "psnr", Severity.MEDIUM, p >= t.psnr_fail_db,
                "PSNR above quality floor" if p >= t.psnr_fail_db else "PSNR below quality floor",
                expected=f">= {t.psnr_fail_db} dB", actual=round(p, 2),
            ))

    if pixel_history_draw_count is not None:
        high = pixel_history_draw_count > t.overdraw_warn
        checks.append(_result(
            "pixel_history_overdraw", Severity.MEDIUM, not high,
            "pixel overdraw detected" if high else "pixel history ok",
            expected=f"<= {t.overdraw_warn} draws", actual=pixel_history_draw_count,
            status=CheckStatus.WARN if high else CheckStatus.PASS,
        ))

    return VerificationReport(layer="L2", checks=checks)


def threshold_verdict(report: VerificationReport) -> str:
    """Collapse a report into a single machine-readable verdict.

    Status-based (not severity-based): any FAIL -> "fail", otherwise any WARN
    -> "warn", otherwise "ok". Returns "skip" when nothing was verifiable
    (empty or all-SKIP report).
    """
    if report.failed():
        return "fail"
    if report.warnings():
        return "warn"
    if report.all_pass():
        return "ok"
    return "skip"


def score_from_report(report: VerificationReport) -> float:
    """Collapse an L2 report into a [0,1] badness score (0 = perfect).

    - rt_hash failure is terminal (1.0).
    - otherwise use the pixel-diff changed fraction.
    - if no pixel-diff evidence exists at all, return 1.0 so the orchestrator
      never mistakes "unverifiable" for "converged".
    """
    for c in report.checks:
        if c.rule == "rt_hash" and c.status is CheckStatus.FAIL:
            return 1.0
    for c in report.checks:
        if c.rule == "pixel_diff":
            frac = c.evidence.get("changed_fraction")
            if isinstance(frac, (int, float)):
                return float(frac)
    return 1.0
