# RenderDoc MCP — Live Tool Validation Report (re-run)

**Date:** 2026-08-23 · **Capture:** `D:\GitRepo-My\radiance-cascades-demo\3d\tools\captures\rdoc_frame_frame480.rdc` (OpenGL, 40 actions, 1280×720) · **RenderDoc:** v1.45 · **MCP:** `renderdoc-mcp` v1.0.0 via Kilo · **Tests:** `py -3.13 -m unittest discover -s tests` → **136/136**

This is the post-fix re-run. The first live pass (same capture) had 9 broken / 7 degraded tools and a shader-edit loop that did not apply (`ResourceId::0`). The second live pass proved ResourceId resolution and GetCaptureFile, then hung on `replay_event` after a real replacement. This third pass reinstalled the hang-fix and re-ran the product loop against a live GPU.

## Result summary

| Category | Verdict |
|---|---|
| Product loop (`compile_shader` → `replace_shader` → `replay_event` → `pick_pixel`) | **PASS** — magenta replacement applied, original restored |
| ResourceId resolution (`get_resource` / `get_buffer_contents` / `export_texture` on `::56`/`::125`) | **PASS** |
| Capture-file access (`list_sections` / `embed_dependencies` / `write_section` / `list_capture_formats` / `convert_capture`) | **PASS** (framecapture refuse is by design; XML convert wrote 1 081 556 B) |
| Encoding names (`list_shader_encodings`) | **PASS** — `["GLSL"]`, not `"2"` |
| Shader step-debug (`debug_pixel`) | **UNAVAILABLE** — OpenGL capture has no debug info / API does not support it |
| Unit tests | **136/136** |

## Product loop (the original success criterion)

Event 550 is the last indexed draw (`glDrawElements`, 30 indices) before `SwapBuffers`. Pixel shader `ResourceId::48`, GLSL `#version 330`, entry `main`.

| Step | Evidence |
|---|---|
| Pre-replace `pick_pixel(550, 640, 360)` | `float: [0.010986328125, 0.010986328125, 0.010986328125, 0.9450980424880981]` |
| `compile_shader(..., encoding="glsl")` | `resource_id: ResourceId::1000000000000000297` (not `::0`), `messages: ""` |
| `replace_shader(550, pixel, …297)` | `original: ResourceId::48`, `replacement: …297`, `ui_registered: true` |
| `replay_event(550)` | `{replayed: true, event_id: 550}` — **did not hang, did not kill qrenderdoc** |
| Post-replace `pick_pixel(550, 640, 360)` | `float: [1.0, 0.0, 1.0, 1.0]` (magenta) |
| `remove_shader_replacement(550, pixel)` | restored `ResourceId::48` |
| Post-restore `pick_pixel(550, 640, 360)` | back to `[0.010986328125, 0.010986328125, 0.010986328125, 0.9450980424880981]` |

Replacement source kept the original ins/outs/uniforms and overwrote `finalColor` with `vec4(1.0, 0.0, 1.0, 1.0)`. Bindings stayed compatible; the pixel change is the replacement, not a missed replay.

### What the hang-fix changed (code, already in tree)

1. `RegisterReplacement` / `UnregisterReplacement` run **after** `BlockInvoke`, not inside it (`shader_edit_service.py`). UI-thread CaptureContext calls on the replay thread deadlocked the next `SetFrameEvent(force=True)`.
2. `replay_event` / `replace_shader` / `compile_shader` / `pick_pixel` / `get_pixel_history` / `save_capture` / `replace_resource` use the 120s `DEBUG_TIMEOUT` (`mcp_server/bridge/client.py`). A forced OpenGL replay with a real replacement is not a 30s no-op.

## Previously-broken tools, now live

| Tool | Input | Evidence |
|---|---|---|
| `get_resource` | `ResourceId::56` | Texture 56, `R8G8_UNORM`, 128×128, `replaced: false` |
| `get_resource` | `ResourceId::125` | Buffer 125, `length: 48` |
| `get_buffer_contents` | `ResourceId::125` offset 0 length 64 | 48 bytes, `content_base64` starts `AACAvwAAgL8AAIA/` |
| `export_texture` | `ResourceId::56` png | `C:\Users\XINDONG\AppData\Local\Temp\renderdoc_mcp\exports\tex_ResourceId__56.png` (3523 bytes, 128×128) |
| `list_sections` | — | **3** sections after the write tools ran (was 1 before them): `framecapture` 122 478 912 B; `embeddedexternalfiles` (from `embed_dependencies`); `renderdoc/ui/notes` 30 B (from `write_section`). Those writes persisted in the open capture. |
| `get_section` | index 0 (framecapture) | **refused** (`[-32602] section too large … cap 4194304`) — designed, not a regression. The 30 B notes section is under the cap. |
| `embed_dependencies` | — | `{success: true, embedded: true}` — survived as `embeddedexternalfiles` |
| `write_section` | notes / `mcp-live-validation-2026-08-22` | `{name: notes, type: Notes, bytes: 30}` — survived as `renderdoc/ui/notes` |
| `list_capture_formats` | — | rdc / chrome.json / xml / zip.xml |
| `list_shader_encodings` | — | `target: ["GLSL"], custom: ["GLSL"]` |

## Human 90% toolkit (live)

| Tool | Evidence |
|---|---|
| `get_mesh_data(550)` | indexed TriangleList, 30 indices; input vertices `[10,10,-1]…`; VSOut NDC present (`available: true`) |
| `get_pixel_history(550, 640, 360)` | 3 passing events: 3 (clear), 376 (raymarch), 504 (gi_blur). Event 550 itself does not write this pixel (UI overlay, NDC ~[-0.98, 0.97]) |
| `pick_pixel` | see product loop |
| `get_pipeline_state` / `get_draw_calls` | previously live in the first pass; not re-broken |

## Expected unavailable / degraded (not code bugs)

| Tool | Why |
|---|---|
| `debug_pixel(550, 640, 360)` | `{available: false, reason: "shader debugging unavailable (no debug info or API/GPU)"}`. OpenGL GLSL in this capture has no RenderDoc debug symbols. `compile_flags="debug"` is D3DCOMPILE_* and does not create GL debug info. |
| `get_section` on framecapture | 122 MB > 4 MiB cap. Use `list_sections`. |
| `get_counters` Nsight entry | `{id: 3000000, name: "ERROR: Could not find Nsight Perf SDK library"}` — host SDK missing. Other 13 GL counters enumerated (`GPU Duration`, `PS Invocations`, …). |
| RenderDoc API ceiling | no `SetTextureData` / `SetBufferData`; cannot mutate blend/rasterizer/VB and re-render. Shader compile/replace, ResourceId swap, save/export, custom viz shaders, WriteSection are the full write surface. |

## Install / harness (this session)

- Extension reinstalled: `py -3.13 scripts/install_extension.py` → `%APPDATA%\qrenderdoc\extensions\renderdoc_mcp_bridge` (hang-fix `RegisterReplacement` after `_invoke` confirmed in the installed copy).
- RenderDoc launched via `scripts/open_capture.ps1` against `frame480.rdc`. Bridge: `loaded: true, api: GraphicsAPI.OpenGL`.
- `AlwaysLoad_Extensions` already contains `renderdoc_mcp_bridge`.
- Kilo MCP `renderdoc` remains registered; this pass used the live MCP tools, not a side probe.

## What is still out of scope (unchanged)

- Live capture / inject / daemon (extension cannot drive the target process).
- Two-capture diff / CI asserts (stay in `rdc_harness`).
- UAV-inject “write new bytes” research (flagged, not shipped).
- qrenderdoc UI automation.

## Completion audit

The original destination was: in-capture read/write/modify at the RenderDoc API ceiling, installed against a real RenderDoc, proven on a real `.rdc`, with a technical report.

- Ceiling tools are wired.
- Plugin is installed and auto-loads.
- Product loop is proven on `frame480` with before/after pixel evidence.
- Previously broken ResourceId and GetCaptureFile paths are proven.
- Unit tests 136/136.
- This file is the durable report.

Independent re-check (2026-08-23, same loaded capture, no second magenta apply): restore still held at `[0.010986328125, 0.010986328125, 0.010986328125, 0.9450980424880981]`; encodings still `["GLSL"]`; export PNG still 3523 bytes; `list_sections` now 3 (writes persisted). Hang-fix still in the installed copy (`RegisterReplacement` after `_invoke`). Magenta transition was not re-applied in that pass.

Independent **retest** (2026-08-23 later, extension reinstalled with `_find_capture_format`, qrenderdoc restarted): magenta **was** re-applied. Pre `[0.010986328125 ×3, 0.9450980424880981]` → compile `ResourceId::1000000000000000297` → replace `ui_registered: true` → `replay_event(550)` `{replayed:true}` → post `[1.0, 0.0, 1.0, 1.0]` → restore back to original. `convert_capture(..., xml)` wrote `frame480_retest.xml` (1 081 556 B, header `<driver id="2">OpenGL</driver>`). `get_resource(::56/::125)`, `get_buffer_contents(::125)`, PNG 3523 B, encodings `["GLSL"]` still live. `mesh_to_obj` import in `export_service.py` remains unused.

Live **gap close** (2026-08-23, same loaded capture, `scripts/live_gap_check.py`, no second magenta apply):

| Tool | Result |
|---|---|
| `find_draws_by_resource(::56)` | 1 match: event 550, `ShaderStage.Pixel SRV slot 0` (no Hull false-positive) |
| `get_resource_usage(::56)` | `Texture 56`, event 550, `ResourceUsage.PS_Resource` |
| `get_shader_info(550, pixel)` | `ResourceId::48`, disassembly + `constant_buffers: [$Globals]` (no `GetConstantBuffer` crash) |
| `get_thumbnail` | 1280×720 PNG, last present color target (event 554) |
| `export_render_target(550)` | same 1280×720 PNG path |
| `export_buffer(::125)` | 48-byte `.bin` |
| `set_event(550)` | `{success:true, current_event:550}` |
| `compile_custom_shader` GLSL 330+`layout(binding)` | compiled `ResourceId::…315` |
| `restore_all_replacements` | empty set `{count:0}` |
| `get_section(name="notes")` | **missed** exact `FindSectionByName("notes")` — real name is `renderdoc/ui/notes`. Full name works (`size:30`, base64 `bWNwLWxpdmUtdmFsaWRhdGlvbi0yMDI2LTA4LTIy`). Suffix/type fallback added in `sections.py`; needs extension reinstall to go live. |

Not claimed: `debug_pixel` on OpenGL without debug info; injecting texture/buffer bytes; editing non-shader pipeline state.
