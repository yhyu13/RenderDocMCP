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
2. get_draw_calls(filtered)     → Unity: preset="unity_game_rendering"
3. Symptom fork (human 90% toolkit — do not dump the frame):
   - wrong pixel  → pick_pixel → get_pixel_history (last passing fragment)
   - mesh wrong   → get_mesh_data (input vs VSOut; if input already bad, stop)
   - invisible    → get_pipeline_state rasterizer/depth_stencil/blend
   - wrong colour → pick_pixel + pipeline blend + PS constants
4. find_draws_by_*() / get_shader_info() only after the fork points at a draw
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
get_draw_calls(preset="unity_game_rendering")
# equivalent: marker_filter="Camera.Render" plus the GUI.Repaint / UIR.DrawChain /
# EditorLoop exclude list. Do not dump the whole Unity Editor frame.
```

### Visual / mesh bugs (prefer these over get_texture_data)

```python
pick_pixel(event_id, x, y)                    # one texel, not the whole RT
get_pixel_history(event_id, x, y)             # who wrote it; last passed=true
get_mesh_data(event_id, max_vertices=8)       # VSIn vs VSOut sample
get_pipeline_state(event_id)                  # rasterizer / depth_stencil / blend
get_resource_usage(resource_id)               # timeline usage strip
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
