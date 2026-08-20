---
name: renderdoc-capture-analysis
description: Inspect a RenderDoc capture efficiently using token-aware filtering, reverse lookups, and structured summaries. Use when exploring .rdc files, finding draws, or diagnosing frame-level rendering issues.
---

# RenderDoc Capture Analysis Skill

## When to use

- A RenderDoc capture (.rdc) is loaded or you need to open one.
- You want to understand the frame: draw calls, markers, GPU timings, resources.
- You need to find which draw calls use a specific shader, texture, or resource.
- You are diagnosing performance bottlenecks or visual artifacts.

## When NOT to use

- No RenderDoc process/extension is available and you cannot launch one.
- The task is pure asset/art authoring without a capture to inspect.
- You only need to edit source code; use the shader-fix skill instead.

## Core idea: token funnel

RenderDoc captures can produce 70 KB+ of raw draw-call JSON. Always descend from the coarsest summary to the smallest detail needed:

```
1. get_frame_summary()          → choose a marker / event range
2. get_draw_calls(filtered)     → narrow to the relevant subtree
3. find_draws_by_*()            → jump directly to suspect draws
4. get_draw_call_details() / get_pipeline_state() / get_shader_info()
   → inspect the specific event
```

Never call `get_draw_calls(include_children=true)` on an entire frame unless the capture is tiny.

## Standard workflow

1. **Confirm capture state**
   - `get_capture_status()`
   - If no capture is loaded: `list_captures(directory)` → `open_capture(path)`.

2. **Get the frame summary**
   - `get_frame_summary()`
   - Read `api`, `statistics`, `top_level_markers`, `render_targets`.

3. **Filter draw calls**
   - Use `marker_filter` to keep a subtree (e.g. `"Camera.Render"`).
   - Use `exclude_markers` to drop UI/editor noise (e.g. `["GUI.Repaint", "UIR.DrawChain"]`).
   - Use `event_id_min` / `event_id_max` after you know the range.
   - Use `only_actions=True` and/or `flags_filter=["Drawcall", "Dispatch"]` to skip markers.

4. **Reverse lookup (if you know the resource)**
   - `find_draws_by_shader(shader_name="Toon", stage="pixel")`
   - `find_draws_by_texture(texture_name="CharacterSkin")`
   - `find_draws_by_resource(resource_id="ResourceId::12345")`

5. **Inspect details**
   - `get_draw_call_details(event_id)`
   - `get_pipeline_state(event_id)` — shaders, SRVs/UAVs, samplers, RTs, viewports.
   - `get_shader_info(event_id, stage)` — disassembly, constant buffers, bindings.
   - `get_action_timings(...)` — GPU duration (may be unavailable on some hardware).

## Presets

### Unity Editor capture — game rendering only

```python
get_draw_calls(
    include_children=True,
    marker_filter="Camera.Render",
    exclude_markers=[
        "GUI.Repaint",
        "UIR.DrawChain",
        "GUITexture.Draw",
        "UGUI.Rendering.RenderOverlays",
        "PlayerEndOfFrame",
        "EditorLoop",
    ],
    only_actions=False,
)
```

### Focused dispatch / compute investigation

```python
get_draw_calls(
    include_children=True,
    only_actions=True,
    flags_filter=["Dispatch"],
)
```

## Best practices

- Prefer `marker_filter` + `exclude_markers` over fetching everything and parsing locally.
- Cache `event_id` ranges; reuse them across `get_draw_calls`, `get_pipeline_state`, `get_shader_info`.
- If `get_action_timings()` returns `available: false`, do not rely on GPU timing data.
- WebGPU captures on the D3D12 backend are inspected as D3D12; shader source is WGSL→HLSL lowering.
