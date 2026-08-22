# RenderDoc Human Experience

> What graphics programmers actually do in RenderDoc — not the feature list, not the agent design docs.
> Research dump 2026-08-21. Sources at the end. This is the spec the two repos should serve.

---

## 0. One-line thesis

**90% of real RenderDoc work is four windows plus one killer feature:** Event Browser, Texture Viewer, Pipeline State, Mesh Viewer — and Pixel History when a single pixel is wrong. Shader stepping, overlays, and hot-reload are secondary. If an agent cannot do that loop, it is not a RenderDoc user.

Baldur Karlsson, Vulkanised 2018: once texture contents, constants, pipeline state, and geometry can be inspected while stepping the frame, you have the core toolkit people use most of the time.

---

## 1. The 90% toolkit (Baldur)

| Window | What a human is asking | Typical next click |
|--------|------------------------|--------------------|
| **Event Browser** | Where am I in the frame? Which pass? | Expand `Camera.Render`, skip editor UI, jump to a draw |
| **Texture Viewer** | What does this RT / input look like *right now*? | Pick a pixel → History / Debug; lock a texture tab |
| **Pipeline State** | What is bound, and is the state insane? | Go-arrow into shader / buffer / texture; check RS / DS / OM |
| **Mesh Viewer** | Is the mesh wrong before or after the VS? | Input vertices vs VS output; click a vertex, read IDX |
| **Pixel History** | Who wrote this pixel, and who failed a test? | Green = wrote, red = rejected; then debug that fragment |

Everything else (ISA, counters, custom viz shaders, resource inspector, timeline) is loaded *after* this loop fails to answer the question.

### Texture Viewer habits that matter

- Thumbnail strip **follows the bound slot** as you step events (Baldur: this is a beloved feature vendor tools often lack).
- **Locked tab** to watch one resource even when it unbinds.
- Right-click pick pixel → status bar numeric value + pixel-context zoom.
- Overlays used as first-pass diagnosis, not decoration:
  - `Highlight Drawcall` — where is this object?
  - `Depth Test` — red fail / green pass
  - `NaN/Inf/-ve`
  - `Quad Overdraw` / `Triangle Size`
  - `Clipping` against black/white points
  - `Clear before Draw/Pass` — isolate a subtle blend
- Custom visualization shaders exist because packed G-buffers are unreadable as RGBA.

### Pipeline State habits

- Humans do **not** dump the whole pipeline. They open VS or PS, then constant buffers, then rasterizer / depth / blend.
- The go-arrow convention is the UX: shader → source/disasm, texture → locked tab, buffer → mesh or raw or CB popup.
- Missing names = missing shader debug info. Unity needs `#pragma enable_d3d11_debug_symbols`.

### Mesh Viewer habits (Matias Lavik — the most repeated practitioner loop)

1. Input mesh wrong → not a shader bug (importer / CPU / `glVertexAttribPointer` size).
2. Input right, output wrong → vertex shader / matrices.
3. Click a vertex, read **IDX**. Degenerate triangles (`5,6,6`) are a real class of bugs.
4. Invalid attributes show as `---` — usually a CPU-side vertex layout bug.

---

## 2. Symptom → first tool (Matias checklist)

This is the decision tree humans actually run. Encode it as recipes, not as "inspect everything".

| Symptom | First tool | Then |
|---------|------------|------|
| Mesh looks wrong / missing faces / distorted | Mesh Viewer (input vs output) | VS constants (matrices); if input already bad, leave GPU tools |
| Colours wrong | Texture Viewer (inputs) | Mesh UVs/normals; PS constant buffers; blend state |
| Nothing rendered | Event Browser + API Inspector + Errors and Warnings | Viewport/scissor, cull, depth, `ColorWriteMask == 0`, empty draw |
| One pixel / speck / hole | **Pixel History** | Last *passing* fragment → pixel shader debug |
| Shadows acne / peter-pan / missing | Shadow-pass RT export | Depth bias in rasterizer; light matrices in PS constants |
| Poor FPS | Event Browser (extra camera?) + Statistics + GPU timings | Nsight/PIX for real SOL/trace — RenderDoc timings are estimates |
| "What is this engine doing?" | Marker tree + step + Texture Viewer | e.g. Unity shaded wireframe = opaque pass + `Fill Mode: Wireframe` |

Pixel History is the feature people call a **killer feature**: green = modified, red = test-failed. Overdraw of the same pixel: debug the last depth-passing fragment unless you pick from history.

---

## 3. Engine-specific human workflows

### Unity Editor (the noise problem)

This is the #1 token and UX failure mode for agents *and* humans.

- Load RenderDoc from Game/Scene tab; **pause, then capture**.
- Event names differ for editor Game view vs Scene view vs player.
- **The subtree you want is `Camera.Render`.**
- Ignore / exclude: `GUI.Repaint`, `UIR.DrawChain`, `GUITexture.Draw`, `UGUI.Rendering.RenderOverlays`, `PlayerEndOfFrame`, `EditorLoop`.
- GPU timings: clock button in Event Browser; editor draws are mixed in — filter first.
- Shader property names need `#pragma enable_d3d11_debug_symbols`.

### Unreal

- Plugin capture button on the viewport; or `RenderDoc.CaptureFrame` in PIE (viewport UI is gone).
- `Capture all activity` pulls editor UI and thumbnail previews — usually unwanted.
- `Reference all resources` / `Save all initial states` explode capture size (GBuffer initials often stripped by heuristic).
- Launching `UE4Editor.exe` from RenderDoc: enable **Capture Child Processes**.
- `-AttachRenderdoc` can change Insights visibility (`r.ShowMaterialDrawEvents`); capture tools change the frame.

### Browser / WebGPU / WebGL (this repo's own field notes)

- No native WebGPU backend: Chrome D3D12 process inject, or WebGL as D3D11/ANGLE.
- `--gpu-startup-dialog` is dead on Chrome ≥ ~120; working WebGL recipe is `--in-process-gpu` + keep-alive capture.
- rdc-cli `shlex.join` corrupts Windows `\` paths — forward slashes only.
- Named sessions: parallel agents steal the default daemon.

---

## 4. Capture hygiene (Jeremy Ong + Baldur)

These are not optional niceties. Without them the 90% toolkit is a haystack.

1. **Named resources** (`SetName` / debug utils). Unnamed descriptor heaps are unusable.
2. **Nested debug markers / scopes** with colour. A 5k-event flat list is not a workflow.
3. **Programmatic capture** in every tool (PIX, RenderDoc, Nsight). Visual bugs are timing-dependent.
4. **Freeze simulation, free camera** after freeze — for view-dependent systems.
5. **Shader debug info on disk and searchable** (`/Zi`, `/Od`, `-Fd`; Vulkan `-gVS` / `-fspv-debug=vulkan-with-source`). Stripped blobs = no names, no source debug.
6. **Shorten the edit loop.** Clone a material header rather than recompile the world.
7. Shader debugging is **D3D11 / D3D12 / Vulkan only**. Wave/quad intrinsics often make pixel debug lie or disable it.
8. Dump buffers to CSV when the UI table is the wrong tool.

---

## 5. Heisenbugs and the FAQ humans hit

From RenderDoc FAQ + practitioner posts:

| Failure | What it actually is |
|---------|---------------------|
| "RenderDoc makes my bug go away" | Overlay + extra memory + Map() interception + 1–2 very slow frames. Timing bugs vanish. |
| Replay ≠ capture | Replay is not a perfect reproduction and cannot be. |
| Invalid API use | RenderDoc is not a validator. Validation layers first. Invalid use breaks the debugger the same way it breaks drivers. |
| Capture attached changes UE Insights / material events | Tools inject extra named events. Don't treat capture-on as ground-truth perf. |
| GL shader debugger | Offered as-is; many bugs will not be tractable. Still report with repro. |
| Pixel debug error with no cause | History may use a flipped Y; unhelpful "Error debugging pixel" is a known UX hole. |
| UI forgets expansion/selection | Comparing a buffer before/after an event is painful; change-highlight is requested and low-priority. |

Mitigations humans use: disable async compute / threaded recording when the bug disappears under a capture tool; in-engine RT visualization without a capture; shader printfs / UAV debug buffers.

---

## 6. RenderDoc vs PIX vs Nsight (role split)

Humans juggle tools. Do not pretend RenderDoc replaces them.

| Job | First tool | Why |
|-----|------------|-----|
| "Why is this pixel / mesh / binding wrong?" | **RenderDoc** | Best visual debugger UX; overlays; pixel history; shader edit |
| Desktop GPU bottleneck / SOL / trace | **Nsight Graphics** | GPU Trace, SM stalls; RenderDoc timings are coarse |
| D3D12/Xbox, shader PDB reload, PIX captures | **PIX** | Often more stable on RT / exotic D3D12 |
| Ray tracing / crashy RD sessions | Nsight or PIX | RenderDoc RT gaps; crashes on exotic features |
| Android | Sokatoa first (2026 reports), then RenderDoc remote | RD Android support felt dated; still works |

Jeremy: "Nsight is generally the best tool for debugging perf issues (if developing for desktop)." Matias: same, with the NVIDIA SOL articles as required reading. RenderDoc's clock is for *which draw is expensive*, not *which hardware unit*.

---

## 7. What people praise (do not break these)

1. Stepping the Event Browser **live-updates** resource views (issue #3496: vendor tools often require reopen).
2. Pixel History turns "one pink pixel in 2M" into a deterministic list.
3. Overlay + locked texture tab while browsing draws.
4. Shader edit/replace without restarting the app.
5. Consistent UI across D3D11/12/Vulkan/GL.
6. Baldur's response time on GitHub (survey 2016 still matches the culture).

---

## 8. What people fight (agent-visible)

1. **Editor/UI noise** in Unity/UE captures — the MCP proposal already named this; it is still the top workflow.
2. **Nameless objects** without debug info / `SetName`.
3. **Giant buffers** with no change highlighting — humans scroll; agents must diff or sample.
4. **Pixel debug / GL debugger opacity** — errors without cause.
5. **Heisenbugs** under capture.
6. **Wave intrinsics** vs shader debugger.
7. **Token bombs**: full `get_draw_calls(include_children=true)` and full texture bytes. Humans never "read the whole frame"; they filter, then pick one pixel.

---

## 9. Implications for these two repos

### RenderDocMCP must expose the 90% toolkit, not only the data-access leftovers

Before this work, the bridge had draw lists, pipeline (shaders/SRVs/CBs/RTs), raw texture/buffer bytes, timings, shader edit. **Missing the human loop:**

| Human action | API | Status (2026-08-21) |
|--------------|-----|---------------------|
| Pick this pixel | `PickPixel` | `pick_pixel` MCP tool |
| Who wrote this pixel? | `PixelHistory` | `get_pixel_history` (capped) |
| Mesh input vs VS output | `GetPostVSData` + VSIn from IA | `get_mesh_data` (sampled) |
| Cull / fill / depth func / ColorWriteMask | `GetRasterState` / `GetDepthTestState` / `GetColorBlends` | on `get_pipeline_state` |
| Usage in frame (timeline) | `GetUsage` | `get_resource_usage` |
| Unity game-only subtree | `preset=unity_game_rendering` | implemented |

### renderdoc-skill must teach the human decision tree

Recipes already exist (invisible, wrong colour, shadows, pixel, perf). Gaps:

- Matias **input-vs-output mesh** as the first step for geometry, not "debug vertex 0".
- Unity `Camera.Render` + exclude-marker list as a default, not a buried MCP-only preset.
- Heisenbug / shader-debug-info / tool-role-split as capture prerequisites.
- Overlays and pixel history as first-class, not "also rdc pixel".
- Pixel history **before** full shader traces (traces are 10k–15k steps; humans open history first).

### Token rule that matches humans

Humans never load a 4K texture as numbers. They pick one pixel. Agents should:

1. `get_frame_summary` → marker filter
2. For visual bugs: `pick_pixel` / `get_pixel_history` (tiny JSON)
3. For mesh bugs: 8 sample vertices in + out, not the whole VB
4. For invisible: rasterizer + depth + blend + viewport, not full disassembly
5. Full `get_texture_data` / `--trace` only after the above points at a cause

---

## 10. Sources

| Source | Why it counts as "human experience" |
|--------|-------------------------------------|
| Baldur Karlsson, RenderDoc history + Vulkanised 2018 | Author; "90% toolkit"; UI is half the problem |
| RenderDoc docs: Quick Start, Texture Viewer, Pixel History, How do I debug a shader, FAQ | Canonical workflow, overlays, heisenbug FAQ |
| Matias Lavik, "Graphics Debugging using RenderDoc" (2020) | Practitioner checklist + three real cases (missing faces, attrib size, Unity wireframe) |
| Jeremy Ong, "Debugging For Graphics Programmers" (2021) | Capture hygiene, freeze+camera, RD vs Nsight, wave-intrinsics trap |
| Unity Manual: RenderDoc integration; TheGamedev.Guru GPU timings | Pause-then-capture; `Camera.Render`; editor noise |
| Epic: Using RenderDoc with Unreal; Temaran plugin | Child processes, capture-all-activity size trap |
| GitHub baldurk/renderdoc #3496, #3763 | Live resource update praise; pixel-debug error UX; GL debugger limits |
| Johannes Unterguggenberger, Android GPU debugging (2026) | RD vs Nsight vs PIX vs Sokatoa; crash/juggle tools |
| wunkolo, GPU Debug Scopes (2024) | Unnamed events = unusable Event Browser |
| LunarG / Vulkanised 2023, source-level shader debugging | `/Od`, `-gVS`, `-fspv-debug=vulkan-with-source`; step-back is emulated |
| This repo JOURNEY (WebGL ReSTIR, 2026-08-19) | Chrome capture failures; named sessions; texture initial contents = 0 until `SetFrameEvent` |

---

## 11. Non-goals

- Do not turn RenderDoc into a profiler. Point at Nsight/PIX.
- Do not implement buffer change-highlight in the extension (Baldur: low priority, hard at buffer scale).
- Do not add socket IPC (embedded Python 3.6 has no sockets).
- Do not dump full mesh/texture bytes into the LLM context by default.
