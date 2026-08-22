"""GPU-free helpers for the human 90% RenderDoc toolkit.

Mirrors what graphics programmers actually click (see
``renderdoc-skill/renderdoc-human-experience.md``): pick a pixel, read
pixel history, sample mesh in vs out, apply the Unity Camera.Render
filter. None of this imports ``renderdoc``; the extension reimplements
the same shapes against the real API.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

UNITY_GAME_RENDERING_PRESET = "unity_game_rendering"

UNITY_EXCLUDE_MARKERS = (
    "GUI.Repaint",
    "UIR.DrawChain",
    "GUITexture.Draw",
    "UGUI.Rendering.RenderOverlays",
    "PlayerEndOfFrame",
    "EditorLoop",
)

UNITY_MARKER_FILTER = "Camera.Render"

KNOWN_DRAW_PRESETS = (UNITY_GAME_RENDERING_PRESET,)


def resolve_draw_filters(
    preset: Optional[str] = None,
    marker_filter: Optional[str] = None,
    exclude_markers: Optional[Sequence[str]] = None,
) -> tuple[Optional[str], Optional[list[str]]]:
    """Expand a named capture preset into marker filters.

    Explicit ``marker_filter`` / ``exclude_markers`` win as the base;
    the Unity preset fills in missing filter and *unions* exclude lists
    so a caller can add extra noise markers without dropping the defaults.
    """
    if not preset or preset == "none":
        if exclude_markers is None:
            return marker_filter, None
        return marker_filter, list(exclude_markers)

    if preset != UNITY_GAME_RENDERING_PRESET:
        raise ValueError("unknown draw preset: %s" % preset)

    if marker_filter is None:
        marker_filter = UNITY_MARKER_FILTER

    merged: list[str] = list(UNITY_EXCLUDE_MARKERS)
    if exclude_markers:
        seen = set(merged)
        for name in exclude_markers:
            if name not in seen:
                merged.append(name)
                seen.add(name)
    return marker_filter, merged


def decode_position_vertices(
    data: bytes | bytearray | memoryview,
    stride: int,
    count: int,
    float_offset: int = 0,
) -> list[list[float]]:
    """Decode tightly packed float4 positions (SV_Position first on VSOut).

    RenderDoc shuffles the builtin position to the front of post-VS data.
    ``float_offset`` is a byte offset into each vertex (default 0).
    """
    import struct

    if stride <= 0 or count <= 0:
        return []
    need = 16
    out: list[list[float]] = []
    buf = memoryview(data)
    for i in range(count):
        start = i * stride + float_offset
        if start + need > len(buf):
            break
        out.append(list(struct.unpack_from("<ffff", buf, start)))
    return out


def ndc_xy(position: Sequence[float]) -> Optional[list[float]]:
    """Clip-space [x,y,z,w] → NDC xy, or None if w is 0."""
    if len(position) < 4:
        return None
    w = float(position[3])
    if w == 0.0:
        return None
    return [float(position[0]) / w, float(position[1]) / w]


def serialize_pixel_modification(mod: Any) -> dict[str, Any]:
    """Attribute-duck-typed PixelModification → JSON (extension + tests)."""

    def _color(pixel_value: Any) -> Optional[list[float]]:
        if pixel_value is None:
            return None
        fv = getattr(pixel_value, "floatValue", None)
        if fv is None:
            return None
        return [float(c) for c in fv[:4]]

    def _mod_value(mv: Any) -> dict[str, Any]:
        if mv is None:
            return {"valid": False}
        valid = True
        is_valid = getattr(mv, "IsValid", None)
        if callable(is_valid):
            valid = bool(is_valid())
        col = getattr(mv, "col", None)
        return {
            "valid": valid,
            "color": _color(col),
            "depth": getattr(mv, "depth", None),
            "stencil": getattr(mv, "stencil", None),
        }

    passed = getattr(mod, "Passed", None)
    passed_v = bool(passed()) if callable(passed) else bool(getattr(mod, "passed", False))
    return {
        "event_id": getattr(mod, "eventId", None),
        "passed": passed_v,
        "frag_index": getattr(mod, "fragIndex", 0),
        "primitive_id": getattr(mod, "primitiveID", 0),
        "pre": _mod_value(getattr(mod, "preMod", None)),
        "shader_out": _mod_value(getattr(mod, "shaderOut", None)),
        "post": _mod_value(getattr(mod, "postMod", None)),
        "failed": {
            "depth": bool(getattr(mod, "depthTestFailed", False)),
            "stencil": bool(getattr(mod, "stencilTestFailed", False)),
            "backface": bool(getattr(mod, "backfaceCulled", False)),
            "scissor": bool(getattr(mod, "scissorClipped", False)),
            "shader_discard": bool(getattr(mod, "shaderDiscarded", False)),
            "depth_clip": bool(getattr(mod, "depthClipped", False)),
            "viewport": bool(getattr(mod, "viewClipped", False)),
            "sample_mask": bool(getattr(mod, "sampleMasked", False)),
            "unbound_ps": bool(getattr(mod, "unboundPS", False)),
            "predication": bool(getattr(mod, "predicationSkipped", False)),
            "direct_shader_write": bool(getattr(mod, "directShaderWrite", False)),
        },
    }


def cap_history(
    events: Iterable[Mapping[str, Any]],
    max_events: int = 32,
) -> dict[str, Any]:
    """Token cap for pixel history (humans expand one row at a time)."""
    items = list(events)
    truncated = len(items) > max_events
    kept = items[:max_events]
    passing = sum(1 for e in kept if e.get("passed"))
    return {
        "count": len(items),
        "returned": len(kept),
        "truncated": truncated,
        "passing": passing,
        "events": kept,
    }
