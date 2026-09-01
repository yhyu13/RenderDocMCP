# JOURNEY — RenderDoc Agent Verification & Fix Harness

> Project history in two-column form. **Me** = the human driving; **You** = the agent partner.
> Started 2026-08-18. The three spec documents live in `renderdoc-skill/`; the implementation
> landed in this repo, `RenderDocMCP/rdc_harness/`.

## The spec documents (requirements)

- `renderdoc-agent-interview-guide.md` — token funnel, MCP-vs-Skill split, anomaly rules, SAM chunking, semi-transparent particles.
- `renderdoc-AI-Agent-token高效指南.md` — Layer1/Layer2/Resource summaries, auto-red-flags, early-stop.
- `renderdoc-perception-agent-design.md` — L1 deterministic + L2 behavioral verification, shader edit/replay loop, fix report.

## Two-column log

| Me | You |
|---|---|
| Handed the 3 spec docs and asked: do `renderdoc-skill/` and `RenderDocMCP/` meet them? Then (1) plan the gap closure + double-check best practice, (2) execute + build, (3) self-critic + improve. "Long task, set goals." | Read all 3 docs and both repos end-to-end. Gap analysis: both repos expose only MCP **data-access** tools; all 3 docs converge on a missing **orchestrator + double-layer (L1/L2) verification + report** glue, plus an auto-red-flags rule engine (Doc2 §10.2, Doc1 §2.2, Doc3 §3). |
| — | Proposed the plan: build a pure-Python, RenderDoc-agnostic `rdc_harness/` in `RenderDocMCP`. Rationale: `renderdoc` module isn't installed here → the logic must be GPU-free and unit-testable; Doc3 §3.3 mandates "deterministic checks before model" (zero-model rules). RenderDoc I/O sits behind `ShaderBackend`/`ShaderPatcher` protocols. |
| — | Built `rdc_harness/` (`models` / `rules` / `behavioral` / `summarize` / `orchestrator` / `report`) + 5 test files. Fixed two test-fixture bugs (bottleneck fixture was actually 57% pixel-shader; orchestrator returns the *final* patched source, not the original). 40 tests green. |
| — | Self-critic round 1: added numpy fast path to `pixel_diff`/`psnr` (with pure-Python fallback + parity test), fixed `score_from_report` no-signal→1.0 so "unverifiable" can't read as "converged", removed unused imports. 40 tests + end-to-end demo. |
| Critic #1 (P0/P1/P2): wheel `packages` excludes `rdc_harness`; no process-placement note (must not import from RenderDoc's Python 3.6 extension); `rt_hash` copies the buffer; `run_behavioral` no short-circuit on hash mismatch; `rule_bandwidth` + `check_min_lod` false-PASS on missing data; `report.py` untested; orchestrator boundary untested; no test runner/CLI. | Fixed all: added `rdc_harness` to wheel packages, `__init__` process note, zero-copy `rt_hash`, hash-mismatch short-circuit, bandwidth/min_lod guards (this caught a real `None`-append bug in `run_deterministic`), `test_report.py`, `max_round=0` + history-content tests, `ShaderPatcher.patch` contract, `__main__.py` CLI with `utf-8-sig` BOM handling, `test_cli.py`. 57 tests green. |
| Accepted `/review uncommitted`. | Ran the review: 9 findings (5 WARNING + 4 SUGGESTION). Recommendation: NEEDS CHANGES. |
| Critic #2: confirmed all 9 findings, added one more (`rule_setpass_rt` missing-data shape), gave a recommended fix order. | Implemented in order: `OverflowError` catch in `_num`; `pass_threshold` default 0.05→0.01 (WARN boundary); SKIP emission for the 8 frame-level rules + non-vacuous `all_pass()`; single-pass `_compute_stats` (int16 diff + int32 squares — no float64, no duplicate full passes, no `bytes()` copies); status-based `threshold_verdict`; `_result` dedup (imported from `rules`); removed unused imports. 63 tests green. |
| Critic #3: verified 8/8 fixes against source; flagged "why 1.0 by default" in `score_from_report` as worth a comment. | Pointed out the `score_from_report` docstring already documents it ("no pixel-diff evidence → 1.0 so the orchestrator never mistakes 'unverifiable' for 'converged'"); kept the *semantic* sentinel question deferred to P3. |
| Acknowledged ("Critic closed.") and asked to dump this `JOURNEY.md`. | Wrote it to both repos. |
| We have `rdc_harness` but the RenderDoc-side I/O is all `NotImplementedError`. "Can we wire it up?" | Verified doc3 §4.3 against the RenderDoc v1.45 Python API reference: `SetShaderBytes` / `ReplayEvent` **do not exist** in the bindings. Real flow: `BuildTargetShader(entry, enc, source, flags, stage) → (ResourceId, messages)` → `ReplaceResource(original, compiled)` → `SetFrameEvent(eventId, force=True)`; `RemoveReplacement` reverts. |
| — | Adapted `ShaderBackend` (`compile_shader → bytes` → `→ str` handle) and added the missing glue: `ShaderEditService` (compile / replace / replay / remove / debug-messages / get-source) + 6 new MCP tools + facade/request-handler wiring; filled `RenderDocShaderBackend` bodies (bridge-driven `run_l1`/`run_l2`). 71 tests green. |
| Accepted `/review uncommitted`. | Review: 5 findings (1 WARNING + 4 SUGGESTION) — L2 assumes RGBA8; `get_shader_source` returns binary not editable source; double replay per round; `run_l1` omitted `GetDebugMessages`; dead `_stage`. |
| "Fix all issues." | Fixed: L2 format/size guards; `is_source_text` flag + clarified docs; `replace_shader` force=False; new `check_validation_messages` rule + `run_deterministic(debug_messages=...)`; removed dead `_stage`. 74 tests green. |
| "git add + push", then "README → 中文, update what we did, update JOURNEY, push." | Committed `c179423` + pushed `origin/main`; translated README to Chinese (new tools + loop + `rdc_harness`); updated JOURNEY in both repos. |
| "No AGENTS.md for AI agent onboarding?" | Added `AGENTS.md` (project architecture, hard Python 3.6/3.10 boundary, IPC design, test/lint commands, wheel-deliverable scope). Pushed `438bf62`. |

## Final state

- **Deliverable**: `RenderDocMCP/rdc_harness/` — a RenderDoc-agnostic, GPU-free, unit-tested verification + shader-fix orchestrator core, now backed by a bridge-driven `RenderDocShaderBackend` and a `ShaderEditService` on the extension side (the RenderDoc-side I/O is wired end-to-end).
- **Coverage**: Doc1 (token funnel + MCP/Skill split + anomaly rules), Doc2 (Layer1/Layer2 summaries + `auto_red_flags`), Doc3 (L1 deterministic + L2 behavioral + shader edit/replay loop + fix report).
- **Tests**: 74/74 pass (`python -m unittest discover -s tests`), `py_compile` clean.
- **Deferred (P3)**: `check_binding_completeness` docstring drift; `score_from_report` no-signal sentinel *semantics*; `rule_setpass_rt` missing-data shape; `ShaderCompileFlags` default (`rd.ShaderCompileFlags()` vs int) unverified against a real binding.
- **Future work**: run the full loop against a real RenderDoc/GPU to validate `BuildTargetShader` / `ReplaceResource` / `SetFrameEvent`; golden-baseline management (doc3 open question); `get_debug_messages` queue-draining semantics.

---

## Cross-repo workstreams

The **WebGPU capture** workstream (Chrome D3D12 process-injection capture, `capture_webgpu.py`, `references/webgpu-capture.md`, `12_ddgi` recipe) landed in `renderdoc-skill/`. This repo's contribution was a one-line WebGPU(D3D12) compatibility note in the README — the extension runs in RenderDoc's Python 3.6 sandbox and can't drive Chrome. See `renderdoc-skill/JOURNEY.md` for the workstream.

---

## Human 90% toolkit (2026-08-21)

> Research dump lives in sibling `renderdoc-skill/renderdoc-human-experience.md`. Baldur's 90% loop is Event Browser / Texture Viewer / Pipeline / Mesh Viewer + Pixel History. The bridge had data-access leftovers but not that loop.

| Me | You |
|---|---|
| "search web for renderdoc human experience, dump them to doc, then improve both repo" | Dumped practitioner workflow (Baldur, Matias Lavik, Jeremy Ong, Unity/UE docs, FAQ, GitHub issues) into `renderdoc-skill/renderdoc-human-experience.md`. Mapped gaps: no pick_pixel, no pixel history, no mesh in/out, pipeline missing RS/DS/OM, Unity preset proposed but unimplemented. |
| — | MCP: `PixelService` / `MeshService`; `pick_pixel`, `get_pixel_history` (cap 32), `get_mesh_data` (sample 8 verts), `get_resource_usage`; `get_pipeline_state` now includes rasterizer/depth_stencil/blend; `get_draw_calls(preset="unity_game_rendering")`. L1 `check_invisible_pipeline` (write_mask 0 / empty viewport / FrontAndBack cull). `rdc_harness.human_toolkit` is GPU-free. 100 tests green after indexed-draw + SKIP follow-up (`py -3.13`). |

### Deliverables

- New tools: `pick_pixel`, `get_pixel_history`, `get_mesh_data`, `get_resource_usage`.
- `get_draw_calls(..., preset="unity_game_rendering")`.
- Pipeline JSON: `rasterizer`, `depth_stencil`, `blend`.
- L1 rule `check_invisible_pipeline`; tests in `tests/test_human_toolkit.py`.

---

## In-capture write / rdc-cli parity phases 1–5 (2026-08-22)

> Destination: in-capture API parity. Live capture / inject / daemon stay out. Two-capture diff and CI asserts stay in `rdc_harness`.

| Me | You |
|---|---|
| "can we add write feats (e.g. edit shaders) and so on fully control renderdoc mcp read/write modify" | Shader compile/replace/replay already existed. Locked destination: phases 1–5 in this repo (session/export, shader-step debug, generic ReplaceResource, shader extras, counters/snapshot/VFS). Approach A: one MCP tool per op. |
| Critic: partial-blend PASS over-claim; stale JOURNEY 91; vertex_span `* 16`; get_bytes None; `SetFrameEvent(force=False)` on pick/history. "respond to critic and finish rest phases no questions ask no stop" | Confirmed pick/history already `force=True`; blend PASS only claims `write_mask` when *every* target has it (`test_cull_plus_partial_blend_does_not_claim_write_mask`); `get_bytes` None-check + `* 16` comment already in `mesh_address`. Wired remaining tools through facade → request_handler → `@mcp.tool`. Debug tools use 120s file-IPC timeout. GPU-free tests in `tests/test_write_tools.py`. |

### Deliverables

- Session: `close_capture`, `save_capture`, `set_event`.
- Export: `export_texture`, `export_render_target`, `get_thumbnail`, `export_buffer` (path in JSON, never image/buffer bytes).
- Debug: `debug_pixel` / `debug_vertex` / `debug_thread` (capped states, always `FreeTrace`).
- Resources: `list_resources`, `get_resource`, `replace_resource`, `restore_resource`, `restore_all_replacements`, `get_texture_stats`.
- Shader extras: `list_shader_encodings`, `list_shaders`, `shader_map`, `search_shaders`, `compile_custom_shader`.
- Analysis: `get_counters`, `get_snapshot`, `list_sections`, `get_section`.
- Out of scope (unchanged): live capture/inject; two-capture diff.

---

## Write-surface hardening (2026-08-22, critic follow-up)

> Destination unchanged: in-capture API ceiling. RenderDoc still cannot inject texture/buffer bytes or edit non-shader pipeline state.

| Me | You |
|---|---|
| Critic of write expansion: `get_texture_stats` CPU byte loop is a timeout/HDR footgun; `replace_resource` docstring vs `RegisterReplacement`; `get_section` materializes full section; dead `DebugPixel` fallback; `_FILE_TYPE_MAP` dup; `WriteSection` unused. | Switched stats to GPU `GetMinMax`/`GetHistogram` (format-aware, NaN/Inf flags). Kept RegisterReplacement and documented it as the persist path. `get_section` refuses >4 MiB. Dropped dead fallback. Deduped file-type map. Added `write_section` (notes/bookmarks/resrenames/unknown, 64 KiB cap). GPU-free tests for tex_stats/sections/write_section. |

### Hard ceiling (unchanged)

- Can: compile/replace shaders, swap ResourceIds, save/export, custom viz shaders, write small capture sections.
- Cannot: `SetTextureData` / `SetBufferData`; edit blend/rasterizer/vertex buffers and re-render.

---

## Beyond the replay ceiling (2026-08-22)

> Ranked next: compile_flags → CaptureFile writes → patch/golden export. UAV-inject research deferred.

| Me | You |
|---|---|
| "push further" ranked: (1) fix→patch + golden baselines, (2) Convert/EmbedDependencies, (3) compile_flags, (4) UAV-inject research not a tool. | (3) `compile_shader(..., compile_flags="debug")` → D3DCOMPILE_DEBUG+SKIP_OPTIMIZATION. (2) `embed_dependencies` / `remove_dependencies` / `list_capture_formats` / `convert_capture`. (1) `rdc_harness.export`: unified diff + `.hlsl` + hashed golden RT store. UAV-inject not shipped. Real-GPU loop still the remaining validation. |
| Live OpenGL `frame480` validation: 9 broken, 7 degraded. Shader edit loop returns `ResourceId::0`. | Root causes: (a) `ResourceId.id` is private — `rid.id = n` forges Null; resolve by scanning live objects + compile cache. (b) `GetCaptureFile` is on `ReplayManager`, not `CaptureContext`. Also: `GetConstantBlock` not `GetConstantBuffer`; encoding/format Name(); `num_mips` sanity; GLSL custom-shader `#version 420`. |

---

## Live OpenGL capture: ResourceId::0 + GetCaptureFile wall (2026-08-22)

> Capture: `rdoc_frame_frame480.rdc` (OpenGL, 40 actions, 1280×720), RenderDoc v1.45. 46 tools: 30 pass / 7 degraded / 9 broken. The shader-edit loop (the product) did not apply.

| Me | You |
|---|---|
| Full MCP tool validation against live OpenGL capture. Shader edit loop: `replace_shader` returns `ResourceId::0`, `pick_pixel` unchanged after replay. Export/buffer/get_resource all fail for IDs that `get_texture_info` accepts. Nine tools: `GetCaptureFile unavailable`. | Two root causes, both confirmed in v1.45 headers/docs. (a) C++ `ResourceId.id` is private — forging `rd.ResourceId(); rid.id = n` stays Null; Hull-stage false matches were `Null == Null`. Fix: scan live `GetTextures`/`GetBuffers`/`GetResources` + cache compile-time ResourceIds. (b) `GetCaptureFile` is on `ReplayManager` (`ctx.Replay().GetCaptureAccess()`), not `CaptureContext`. Also patched: `GetConstantBlock`, encoding/format names, `num_mips` 1–32 clamp, thumbnail via `GetOutputTargets`, GLSL custom-shader `#version 420`. 134 tests green (`py -3.13`). |

### Deliverables

- `utils/resource_id.py` — GPU-free numeric parse / Null rejection / encoding+format names / mip sanity.
- `utils/rid_cache.py` — process-local cache of *live* ResourceId objects; `compile_shader`/`list_resources` remember them.
- `utils/capture_access.py` — ReplayManager first, then CaptureContext.
- Call sites no longer assign `rid.id`. `find_draws_by_resource` uses `ids_equal` (rejects Null).
- Reinstall required: `python scripts/install_extension.py` + restart RenderDoc before re-testing `frame480`.

### Live re-run (closed 2026-08-23)

Product loop, ResourceId lookup, GetCaptureFile/ReplayManager, and encoding names all proven on `frame480`. Evidence: `live-tool-validation-frame480.md`. Remaining limits (`debug_pixel` on GL, 4 MiB `get_section` cap, no `SetTextureData`) are API/capture constraints, not open bugs.

---

## Replay-with-replacement hang (2026-08-22, live re-run)

> Live re-test confirmed ResourceId::0 **fixed** (`replace_shader` echoes `ResourceId::1000…297`) and GetCaptureFile **fixed** (`list_sections` returned the 122 MB framecapture). The shader-edit loop still cannot finish: `replay_event` after a real replacement times out / deadlocks.

| Me | You |
|---|---|
| Independent live verification. `replace_shader` now returns the compiled id. Then `replay_event(550)` after replacement: qrenderdoc died once; second attempt timed out, process idle, all later calls timed out. Bare `replay_event` without replacement worked. `list_shader_encodings` still `"2"`. | Two code bugs the live hang exposed. (1) `replace_shader` called `RegisterReplacement` *inside* `BlockInvoke` — UI call on the replay thread; next `SetFrameEvent(force=True)` can deadlock (replay waits for UI, UI waits for replay). `replace_resource` already registered after invoke; `replace_shader` now matches. (2) `replay_event` sat on the 30s DEFAULT_TIMEOUT; a forced OpenGL replay with a real replacement is not a no-op. Moved `replay_event`/`replace_shader`/`compile_shader`/`pick_pixel` to 120s DEBUG_TIMEOUT. Encoding `"2"` mapped via v1.45 ordinal table (GLSL=2). Workaround if replay still hangs: `pick_pixel` already does `SetFrameEvent(force=True)` — skip a separate `replay_event`. |

---

## Live product loop proven (2026-08-23)

> Hang-fix reinstalled. `frame480` reopened. Product loop ran end-to-end on a live GPU. Report: `live-tool-validation-frame480.md`.

| Me | You |
|---|---|
| Idle continuation: do not declare the hang-fix done until `compile_shader → replace_shader → replay_event → pick_pixel` changes a real pixel. | Reinstalled extension, relaunched `qrenderdoc` on `frame480`. Pre-pixel `[0.011,0.011,0.011,0.945]` → compile `…297` → replace (`ui_registered: true`) → `replay_event(550)` `{replayed:true}` → post-pixel `[1,0,1,1]`. Restore returned the original pixel. `get_resource(::56/::125)`, `get_buffer_contents(::125)`, `export_texture(::56)` (3523-byte PNG), `list_sections` (122 MB framecapture), `embed_dependencies`, `write_section`, encodings `["GLSL"]` all live. `debug_pixel` unavailable (no GL debug info). 135/135 tests. |
| Independent re-check of live state (do not re-apply magenta). | Restore still held at original pixel. `list_sections` is **3** (framecapture + `embeddedexternalfiles` + `renderdoc/ui/notes`) — the write tools persisted. Encodings `["GLSL"]`, PNG 3523 B, hang-fix still in installed copy. Report updated. `convert_capture` fallback no longer passes a dict into `ExportCapture` (needs a live `CaptureFileFormat`). Unused `Parsers` imports dropped from export/pixel services. |
| Retest: reinstall + restart + re-apply magenta. | 136/136 tests. Product loop reproduced: `[0.011…]` → `…297` → `{replayed:true}` → `[1,0,1,1]` → restore. `convert_capture` xml wrote 1 081 556 B (`<driver id="2">OpenGL</driver>`). `mesh_to_obj` still unused. |

---

## OpenViking-backed response cache (2026-08-23)

> Task: (1) how can `OpenViking` be useful for caching `renderdoc`; (2) draft plan, self-critic, improve; (3) execute; (4) push.

| Me | You |
|---|---|
| `/goal` for caching `D:\GitRepo-AI\renderdoc` with the OpenViking repo, then plan/self-critic/execute/push. | Read both repos. OpenViking contributes two layers: the lightweight `openviking_sdk.SyncHTTPClient` (persistent `viking://` FS) and RAGFS `CachedFileSystem` (read-through native/Redis/Mooncake cache). RenderDoc MCP has ~60 bridge-backed tools and zero response caching, so every repeated read pays file-IPC + GPU/replay cost. |
| — | Drafted `docs/openviking-cache-design.md`: capture-scoped, read-through cache on the MCP side; memory default, optional OpenViking backend; key = capture identity + method + canonical params; mutations invalidate; queue-draining/exports/debuggers bypass. |
| Self-critic (before code) | 9 risks addressed up front: cross-capture key collision (stat-scoped identity), stale reads after `replace_*` (invalidate on mutation), `get_debug_messages` queue drain (bypass), scope recursion (status bypass-only), SDK absence (lazy import + fallback), semantic-processing waste (`vectors_only` + `read_raw`), oversized entries (4 MiB cap), GPU-free tests (fake bridge), concurrency (locked memory backend). |
| — | Implemented `mcp_server/cache.py` (`MemoryBackend`, `OpenVikingBackend`, `ResponseCache`), wired `config.py` + `server.py` (`RENDERDOC_MCP_CACHE*` env), added `tests/test_cache.py`. |
| Test pass | 154/154 green (`py -3.13 -m unittest discover -s tests`). Caught and fixed two issues during implementation: removed capture-scope memoization (stale key after capture change), and made `OpenVikingBackend.clear()` reset its ready flag so a subsequent `put` re-mkdirs the base. |

### Deliverables

- `mcp_server/cache.py` — read-through `ResponseCache` + memory/OpenViking backends.
- `mcp_server/config.py` / `mcp_server/server.py` — cache wiring and env config.
- `tests/test_cache.py` — GPU-free unit tests (154 total suite).
- `docs/openviking-cache-design.md` — design + self-critique.
- `README.md` / `AGENTS.md` — cache documentation.

---

## Zhihu column pack (2026-08-23)

> Rewrite the live-proven RenderDoc MCP design as a Zhihu 专栏 paste pack (`tech-design-to-zhihu`). `zhihu-cli` can only read 本人创作, not publish.

| Me | You |
|---|---|
| Use `~\.kilo\skills\tech-design-to-zhihu\` to update the Zhihu article, and push. | Two paste packs (知乎 CLI 只能读本人创作，不能发文)。缓存文迁回 OpenViking：`D:\GitRepo-AI\OpenViking\openviking-cache-design-zhihu\`。本仓库只留 `docs/renderdoc-mcp-zhihu/`（产品是像素变了，不是五十个工具）。 |
| Finish remaining live-unproven tools + rewrite Zhihu pack. | Live `frame480` still loaded. Gap script: `find_draws_by_resource(::56)` → Pixel SRV slot 0 (no Hull false-positive); `get_resource_usage` → `PS_Resource` event 550; `get_shader_info` CBs ok; thumbnail + `export_render_target` 1280×720; `export_buffer(::125)` 48 B; `set_event`; `compile_custom_shader` GLSL 330+binding → `…315`; `restore_all_replacements` empty. `get_section("notes")` missed exact name (`renderdoc/ui/notes` works); suffix/type fallback added. Zhihu pack rewritten to skill shape: TL;DR, 错路/脉络/树, 8 PNGs, 收获和结论, PS/PPS/PPPS. 157 tests. |

---

## Competitive research: human expert vs MCP gap (2026-08-29)

> Deliverable: `docs/renderdoc-mcp-competitive-research.md`. Two questions: (1) what can a human expert do to an .rdc that the MCP cannot; (2) can we do single pixel debug and dump the full trajectory.

| Me | You |
|---|---|
| 竞品研究：盘点 55 个 `@mcp.tool`（server.py）对照 human-experience spec，判定"单像素调试能不能做、全轨迹能不能 dump"。 | 90% 循环已全覆盖。真实硬缺口 8 项（排序）：shader 调试只回摘要、GUI overlay、mesh 全量、API Inspector、实时触发捕获、Statistics 聚合、A/B diff、断点交互。结构性缺口 1 个：内嵌 Python 控制台 = 任意脚本，封闭工具面补不齐。 |
| 追问：全轨迹到底卡在哪一层？ | 证据钉死在扩展侧三层截断：`HARD_MAX_STEPS=256`、`HARD_LAST_N=32`、`summarize_state` 只留变量名丢值（debug_trace.py:6-9,56-70,123-144）+ 无条件 `FreeTrace`（debug_service.py:51-55）。RenderDoc 本身给得出 10k–15k 步全轨迹，是打包时扔的。 |
| 方案收敛 | 拒绝提上限回 JSON（token 炸弹，违反 debug_trace.py:3 与 human-experience.md:237 铁律）。推荐方案 C：新工具 `debug_trace_export` 走完整 ContinueDebug 循环、全量写文件（JSONL）、只回 path+统计——与 export_buffer/export_texture 同模式；agent 用 Read 切片。落地骨架 6 条已写进文档，含 120s 长超时与 NaN 清洗注意项。 |

---

## debug_trace_export: full trajectory to file (2026-08-29, go on plan C)

> Decision: competitive research round approved plan C. New tool walks the FULL ContinueDebug loop, serializes every state with before/after values to a JSONL file, returns only path + stats. Same pattern as export_buffer/export_texture (path, never bytes).

| Me | You |
|---|---|
| update journey and go. | TDD: GPU-free red test for full-state serialization + file write + NaN cleaning first, then extension-side walk-to-file (Python 3.6 stdlib only), facade/request_handler wiring, MCP tool with cache bypass, README row. Real-GPU full-trace validation stays open. |

### Result (closed 2026-08-29, live-GPU validation still open)

TDD red (10 failing) → green. utils/debug_trace.py gained clamp_export_limit (hard ceiling 1M, rejects <=0), serialize_state_full, write_trace_file (JSONL: header line + one state per line, NaN/Inf -> string markers), nomalies_for (cap_states refactored onto it, behavior-identical, old tests pin it). debug_service.debug_trace_export walks to natural end (or cap), writes file, returns path+stats only, FreeTrace in finally, catch-all around the walk. Wired facade → request_handler → bridge DEBUG_METHODS (120s) → @mcp.tool debug_trace_export (server.py). Not in CACHEABLE_READ_ONLY → bypasses by design. README row + research doc status added. Critic subagent: BLOCKING=0, 3 MINORs fixed in-round (hard ceiling, max_steps<=0 ValueError, walk catch-all). 170/170 tests (py -3.13); all changed files py_compile OK.

Scope cut: pixel entry only — VS/compute export not built (not requested; shared walk helper makes it +1 wiring each if needed). Open: real-GPU full-trace run on a D3D capture with debug info; NaN-in-response inal_variables nit is pre-existing parity with debug_pixel, left as-is. Reminder: rom ..utils import Parsers in debug_service.py is pre-existing dead import — flagged, not removed.

### Real-rdc validation (2026-08-29, production capture)

Capture: phase12_d/new_rc_split_frame24.rdc (OpenGL, 43.9 MB, the production New RC baseline from the 竞品研究 txt). Flow: reinstalled extension (new debug_trace_export) → restarted qrenderdoc on the split capture → draws shifted to events 184/186, PS ResourceId::48, RT ::229 640x480. Pixel history at (320,240): 2 passing fragments, last writer event 184 shader_out [0.8694461584091187, 1.0164883136749268, 0.8117004036903381, 1.0] — bit-identical to phase12_b's event 166, matching the G9 bit-identical claim. Capped debug_pixel: 12 total steps, names only. Raw file-IPC debug_trace_export (Kilo-side MCP server process still old, so the request went straight to request.json/response.json): {available:true, total_steps:12, truncated:false} → 	race_e184_320_240.jsonl 13 lines (header + 12 states), every change carries full 16-wide before/after VALUES. Cross-checks: step sequence of changed names matches capped output exactly; step 3 _66 after == pixel-history shader_out bitwise; step 2 _65 == pixel-center UV (320.5/640, 240.5/480). First real full-trajectory dump: the agent can now answer WHICH instruction produced the color — impossible from capped tools.

Observations (non-blocking): (a) inal_variables is [] on this GL backend because change fter.name is empty and names live on efore — summarize_state/serialize_state_full have the _var_name(after) or _var_name(before) fallback, inal_variables does not; same empty on pre-existing debug_pixel, left as-is. (b) step values include GPU uninitialized sentinels (-107374176.0) and a denormal (4.2e-45) — normal GL debugger noise. (c) Kilo-side MCP server must be restarted once for debug_trace_export to appear as a tool; extension side is already installed. Helper kept at %TEMP%/kilo/raw_ipc_call.py (mirrors bridge/client.py protocol).

---

## Zhihu pack: debug pixel + full trajectory (2026-08-29)

> Deliverable: docs/renderdoc-mcp-debug-pixel-zhihu/ (article.md + 9 PNGs + PUBLISH.md). Skill: tech-design-to-zhihu. Main line: the human single-pixel debug chain ported to the agent, with the agent taking the last step (full trajectory) further than the GUI.

| Me | You |
|---|---|
| 能生成 debug pixel 文档吗，需要图。 | 3 张实拍直接从在线捕获导出（final-frame 640x480、C0 atlas 1024x512；atlas-c5 备用未引用已删）；5 张真数据/示意 PNG 用 HTML+Playwright 渲染（杀手链/错路/脉络/三层截断/树全貌/12 步轨迹/收获总图），file:// 被拦就用 py http.server 8777 绕。HTML 源留在 images/src/ 可再生成。 |
| 双向回读抓到什么 | Pass 1 保真修 3 处：'9 个 GPU 动作'与帧统计不符（补 clear/present）；颜色搬运链含推断（_66→_35 无直接 before/after 证据），改为纯事实'先后出现在六个变量中'；'辐照 atlas'降为'级联 atlas（C0 级）'。Pass 2：禁用词/mermaid/绝对路径扫描 CLEAN；'不是X而是Y'正文 2 处（≤3）；红字图 2 张（03/05，04 改中性色重截）。 |

### Pack facts (all traceable to this session)

- 43.9 MB OpenGL capture, 2 draws (events 184/186) + 7 dispatches, PS ResourceId::48, RT ::229 640x480 R8G8B8A8_SRGB.
- Pixel (320,240): 2 passing fragments, last writer event 184, shader_out [0.8694, 1.0165, 0.8117, 1.0] (G>1 HDR) -> sRGB 0.730.
- trace_e184_320_240.jsonl: 13 lines, 12 states, 16-wide before/after values; step2 _65 = pixel-center UV; color appears in _66/_35/_73/_81/_88/_69 unchanged.
