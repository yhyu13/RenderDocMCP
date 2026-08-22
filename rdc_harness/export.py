"""Close the shader-fix loop back to the source project.

GPU-free: write a unified diff + final .hlsl, and store hashed golden
render-target bytes so a later session can ask "did this regress?".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .behavioral import rt_hash


def shader_unified_diff(
    original: str,
    final: str,
    *,
    fromfile: str = "original.hlsl",
    tofile: str = "fixed.hlsl",
) -> str:
    """Unified diff of two shader sources (empty string if identical)."""
    import difflib

    if original == final:
        return ""
    lines = list(
        difflib.unified_diff(
            original.splitlines(),
            final.splitlines(),
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        )
    )
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def write_shader_patch(
    *,
    original: str,
    final: str,
    dest_dir: str | Path,
    stem: str = "shader_fix",
) -> dict[str, Any]:
    """Write ``{stem}.hlsl`` (final source) and ``{stem}.patch`` (unified diff)."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    hlsl_path = dest / f"{stem}.hlsl"
    patch_path = dest / f"{stem}.patch"
    hlsl_path.write_text(final, encoding="utf-8")
    patch = shader_unified_diff(
        original,
        final,
        fromfile=f"{stem}.orig.hlsl",
        tofile=f"{stem}.hlsl",
    )
    patch_path.write_text(patch, encoding="utf-8")
    return {
        "hlsl_path": str(hlsl_path),
        "patch_path": str(patch_path),
        "changed": original != final,
        "patch": patch,
    }


def write_golden(
    dest_dir: str | Path,
    name: str,
    data: bytes,
    **meta: Any,
) -> dict[str, Any]:
    """Store render-target bytes + a sha256 sidecar under dest_dir."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    bin_path = dest / f"{name}.rgba8.bin"
    json_path = dest / f"{name}.json"
    bin_path.write_bytes(data)
    payload: dict[str, Any] = {
        "name": name,
        "sha256": rt_hash(data),
        "bytes": len(data),
    }
    payload.update(meta)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "path": str(bin_path),
        "meta_path": str(json_path),
        **payload,
    }


def load_golden(dest_dir: str | Path, name: str) -> tuple[bytes, dict[str, Any]]:
    dest = Path(dest_dir)
    bin_path = dest / f"{name}.rgba8.bin"
    json_path = dest / f"{name}.json"
    if not bin_path.is_file():
        raise FileNotFoundError(str(bin_path))
    data = bin_path.read_bytes()
    meta: dict[str, Any] = {}
    if json_path.is_file():
        meta = json.loads(json_path.read_text(encoding="utf-8"))
    return data, meta


def check_against_golden(
    dest_dir: str | Path,
    name: str,
    actual: bytes,
) -> dict[str, Any]:
    """Compare actual RT bytes to a stored golden (hash + size, no pixel dump)."""
    golden, meta = load_golden(dest_dir, name)
    actual_hash = rt_hash(actual)
    golden_hash = meta.get("sha256") or rt_hash(golden)
    return {
        "name": name,
        "match": actual_hash == golden_hash and len(actual) == len(golden),
        "actual_sha256": actual_hash,
        "golden_sha256": golden_hash,
        "size_match": len(actual) == len(golden),
        "actual_bytes": len(actual),
        "golden_bytes": len(golden),
    }


def artifacts_from_fix_report(
    report: Mapping[str, Any],
    original_hlsl: str,
    dest_dir: str | Path,
    stem: str = "shader_fix",
) -> dict[str, Any]:
    """Write patch files from a ``build_fix_report`` result."""
    final = report.get("final_source") or original_hlsl
    out = write_shader_patch(
        original=original_hlsl,
        final=str(final),
        dest_dir=dest_dir,
        stem=stem,
    )
    out["status"] = report.get("status")
    return out
