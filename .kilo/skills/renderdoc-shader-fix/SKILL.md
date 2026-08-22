---
name: renderdoc-shader-fix
description: Edit, compile, replace, and verify a shader inside a RenderDoc capture using the rdc_harness L1/L2 loop. Use when fixing shader bugs or experimenting with shader changes while staying inside the capture.
---

# RenderDoc Shader Fix Skill

## When to use

- A shader bug or visual artifact has been localized to a specific event/stage.
- You want to test a shader edit without rebuilding the original application.
- You need a repeatable compile → replace → replay → verify loop.

## When NOT to use

- The shader source is binary (`is_source_text: false`) and cannot be edited directly.
- You do not have a capture loaded or the target event_id is unknown.
- The change requires application-side data (CBuffer layout changes, new resource bindings) that the capture cannot provide.

## Core idea: closed-loop verification

`rdc_harness` runs a deterministic, GPU-optional loop behind two protocols:

```
compile_shader(original_hlsl, stage)
   ↓
inject_shader(event_id, stage, compiled)
   ↓
replay_event(event_id)
   ↓
run_l1()  ← deterministic rules (validation messages, binding, draw budget, ...)
   ↓ fail → needs_rebuild
run_l2()  ← behavioral: pixel diff / PSNR / RT hash vs golden
   ↓ score <= threshold → ok
patch(original_hlsl, l2_report, history) → next candidate
   ↓
repeat (max_round default 10)
```

The real RenderDoc adapter is `RenderDocShaderBackend`; the loop itself is unit-testable with fake backends.

## Pipeline steps

1. **Read the original source**
   - `get_shader_source(event_id, stage)`
   - Verify `is_source_text: true` and note `encoding`/`entry`.

2. **Design the edit**
   - Keep resource bindings, semantics, and entry signature compatible.
   - Prefer minimal changes; do not change constant-buffer layouts.

3. **Compile**
   - `compile_shader(hlsl=source, stage=stage, entry=entry, encoding=encoding, compile_flags="debug")` when you need `debug_pixel` symbols.
   - Inspect compiler messages on failure.

4. **Replace and replay**
   - `replace_shader(event_id, stage, compiled_resource_id)` — wait for the echoed compiled id, not `ResourceId::0`.
   - `replay_event(event_id)` (120s timeout). OpenGL `frame480` with a real replacement returned `{replayed:true}`. If a later capture hangs, skip the separate replay: `pick_pixel` already calls `SetFrameEvent(force=True)`. Never call `RegisterReplacement` inside `BlockInvoke`.

5. **Verify**
   - `get_debug_messages()` → L1 validation-layer messages.
   - `get_frame_summary()` / `get_pipeline_state()` → deterministic checks.
   - `get_texture_data()` vs a golden → L2 behavioral check.

6. **Iterate or finalize**
   - If L1 fails, rebuild the source.
   - If L2 fails, use the report to patch and repeat.
   - Use `remove_shader_replacement(event_id, stage)` to restore the original.

## Return statuses

| Status | Meaning |
|--------|---------|
| `ok` | L1 passed and L2 score is within threshold. |
| `static_fail` | `compile_shader` failed. |
| `needs_rebuild` | L1 deterministic checks failed (non-shader bug introduced). |
| `exhausted` | Max rounds reached without convergence. |

## Best practices

- Always run L1 before L2; L1 is zero model cost and catches non-shader regressions early.
- Keep `original_hlsl` unchanged as the patcher baseline; feed L2 reports into the patcher.
   - Record the final `source`, `score`, and `history` in a before/after report (`report.py`). Write the engine-side patch with `write_shader_patch` / `artifacts_from_fix_report`.
- Remove shader replacements when the session ends unless you explicitly want to persist them.
- On WebGPU/D3D12 captures, remember the editable source is HLSL, not WGSL.
