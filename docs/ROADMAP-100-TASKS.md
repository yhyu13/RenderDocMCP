# RenderDoc AI-Agent Toolchain — 100-Task Roadmap (P0–P2)

> Cross-repo plan for the RenderDoc GPU-frame-debugging toolchain:
> **`RenderDocMCP`** (MCP server + `rdc_harness` + `renderdoc_extension` — the implementation)
> and **`renderdoc-skill`** (Claude Code skill + capture scripts + design docs — the guidance).
> Status: 2026-09-01. Baseline: `RenderDocMCP` 170/170 tests green (`py -3.13`).

## 0. Persisted goal

Advance the RenderDoc AI-agent toolchain toward **human-expert capability parity**, **production-grade
robustness**, and **broad distribution** — one verified, test-backed, GPU-free-where-possible slice at a time.
The completion bar for this whole plan is not "more tools" but *an agent can reproduce the human 90% loop
and the long-tail expert steps on a real `.rdc`, with every capability backed by a test, and the whole thing
packaged, documented, and benchmarked.*

Priority definitions:

- **P0** — high value, GPU-free or near-free, executable autonomously now, test-backed, no dependency beyond the repo. Completable and verifiable in one session.
- **P1** — medium value; needs a live GPU / RenderDoc / an external step to fully verify, or is a larger multi-file build. Readiness: right after P0.
- **P2** — long-term / exploratory; needs infra (live capture, CI server, marketplace, hardware matrix), is a design study with uncertain ROI, or is a research/publishing track.

Repos: **M** = RenderDocMCP, **S** = renderdoc-skill, **B** = both.

---

## Task list (T001–T100)

### Debug core — dynamic shader debugging (the flagship)
| ID | P | Repo | Task |
|---|---|---|---|
| T001 | P0 | M | `debug_trace_export`: add **compute** (thread) entry — share the walk helper; GPU-free test for serialize/write/limits. |
| T002 | P0 | M | `debug_trace_export`: add **vertex** (VS) entry — same shared walk; GPU-free test. |
| T003 | P0 | M | Fix `final_variables` var-name fallback (GL leaves `changes[].after.name` empty) — use `_var_name(after/before)` like `serialize_state_full`; add test. |
| T004 | P0 | M | Remove pre-existing dead import `from ..utils import Parsers` in `debug_service.py` (flagged earlier, left as-is). |
| T005 | P1 | M | Live-GPU full-trace validation on a D3D capture with debug info (prove the 10k–15k-step export; record file MB + steps). |
| T006 | P1 | M | Add `dump_path` to `debug_pixel/vertex/thread` so a capped query can also write the full walk (unify capped + export paths). |
| T007 | P0 | M | Consolidate the three debug-walk loops + the export walk into ONE `walk()` helper (dedupe `ContinueDebug`/`FreeTrace`/limit logic). |
| T008 | P1 | M | NaN/Inf in `final_variables` response → clean to string markers so JSON serialization never throws. |
| T009 | P1 | M | "no debug info" path → `available:false` + reason, never a half-written file (verify + test). |
| T010 | P2 | M | Breakpoint / interactive-step session API (pause at step N, inspect, continue) — a stateful trace handle. Design first. |

### Verification engine (`rdc_harness` — pure Python, no GPU)
| ID | P | Repo | Task |
|---|---|---|---|
| T011 | P0 | M | `score_from_report` no-signal sentinel: add an explicit comment + a test pinning `1.0` on no-pixel-diff evidence (so "unverifiable" never reads as "converged"). |
| T012 | P0 | M | `check_binding_completeness` docstring drift: align doc with actual behavior. |
| T013 | P0 | M | `rule_setpass_rt` missing-data shape: deterministic SKIP on missing RT, no crash; GPU-free test. |
| T014 | P0 | M | `rule_bandwidth` + `check_min_lod`: confirm guards + add a missing-data test so they can't false-PASS. |
| T015 | P1 | M | `ShaderCompileFlags` default (`rd.ShaderCompileFlags()` vs int) — verify against a real binding on GPU, or add a GPU-free guard. |
| T016 | P1 | M | Golden-baseline lifetime management: hash-sidecar `write_golden`/`check_against_golden` regenerate semantics + docs. |
| T017 | P1 | M | `get_debug_messages` queue-draining semantics: document + test that a call empties the validation queue (affects repeated L1 runs). |
| T018 | P1 | M | Bring two-capture A/B diff into `rdc_harness` as a pure-library compare (currently extension can't). |
| T019 | P0 | M | Lint gate test: `py_compile` all modules + assert no dead imports (`Parsers`, `mesh_to_obj`) — catch drift in CI-like step. |
| T020 | P2 | M | Beyond-PSNR convergence heuristics (perceptual metrics / SSIM-style), replacing "score ≥ threshold" convergence. |

### Tool-surface gaps (from `docs/renderdoc-mcp-competitive-research.md` #2–#8)
| ID | P | Repo | Task |
|---|---|---|---|
| T021 | P1 | M | Texture overlay equivalents (depth-fail red / NaN-Inf / quad overdraw): a custom-shader recipe + a `get_texture_stats` per-region-mask preset. |
| T022 | P1 | M | Mesh full view: `get_mesh_data` all-vertices mode + degenerate-triangle count (GPU). |
| T023 | P1 | M | API Inspector: `get_api_events` (full action list + params) to close the "nothing rendered" evidence gap. |
| T024 | P2 | M | Live trigger capture (F12/`TriggerCapture`/inject) from the extension — currently only rdc-cli/UE recipe can; needs design (ext stays 3.6 sandbox). |
| T025 | P1 | M | Statistics window: `get_resource_stats_top_n(n, sort_by=bytes)` — one-call memory top-N by resource. |
| T026 | P1 | M | A/B diff between two events or captures: `get_pixel_diff` / `capture_diff` (before/after toggle). |
| T027 | P2 | M | Bounded embedded-Python-console passthrough (sandbox + token cap + allowlist) — design for the structural closed-toolface gap. |
| T028 | P0 | M | `debug_trace_export` README/docstring cross-link + mark plan-C status in the competitive-research doc. |

### RenderDoc API correctness / hardening
| ID | P | Repo | Task |
|---|---|---|---|
| T029 | P0 | M | Grep-guard test: forbid any call site assigning `rid.id` (must scan live objects); add an automated check. |
| T030 | P0 | M | Grep-guard: every `GetCaptureFile` use goes through `pick_capture_access()` (ReplayManager first); automated check. |
| T031 | P1 | M | `Descriptor.numMips` garbage guard: 1–32 clamp → fallback to texture `mips`; add test. |
| T032 | P1 | M | Enum-wrapping paths all use `.name`/`.Name()`, never `str(swig_ptr)` (encoding/format); add test. |
| T033 | P1 | M | `RegisterReplacement` must be **outside** `BlockInvoke`: code-order assert that `replace_shader` mirrors `replace_resource`. |
| T034 | P1 | M | Sweep all long ops onto the 120s `DEBUG_TIMEOUT` tier (compile/replace/replay/pick/debug_*); test asserts. |
| T035 | P0 | M | byte-vs-path contract: add a test asserting `export_*`/sections responses never embed image/buffer bytes. |
| T036 | P1 | M | `get_section` 4 MiB cap + name/suffix/type fallback: tests. |
| T037 | P1 | M | OpenGL capture limitations doc: no debug info / GLSL custom-shader `#version 420` handled / `debug_pixel` unavailable. |
| T038 | P2 | M | WebGPU(D3D12) source is Dawn WGSL→HLSL — a mapping note so an agent can reason about WGSL concepts over HLSL sources. |

### Testing & CI
| ID | P | Repo | Task |
|---|---|---|---|
| T039 | P1 | B | GitHub Actions CI: `python -m unittest discover -s tests` on py ≥3.10, cache, artifacts. |
| T040 | P1 | M | Coverage report; close gaps in `report.py` / orchestrator boundary / backend adapters. |
| T041 | P0 | M | One runner (`scripts/test_all.py` or `make test`) that runs the suite + `py_compile` on `mcp_server` and a 3.6-syntax parse of `renderdoc_extension`. |
| T042 | P0 | M | Add GPU-free duck-typed shader-walk test helpers (extend `test_debug_trace_export.py` style) to cover the VS/compute walk + `walk()` consolidation. |
| T043 | P2 | M | Benchmark harness: measure per-tool response size and latency before/after caching (token-savings numbers). |
| T044 | P2 | M | Property-based fuzz of the rule engine on degenerate frames (no crash). |

### Docs & skills
| ID | P | Repo | Task |
|---|---|---|---|
| T045 | P0 | M | Sync `renderdoc-human-experience.md` (stale duplicate in `RenderDocMCP` vs canonical in `renderdoc-skill`); make one canonical, dedupe. |
| T046 | P0 | M | README/AGENTS: add `debug_trace_export` row + competitive-research status; confirm AGENTS reflects it. |
| T047 | P0 | B | Update JOURNEY with this round + a pointer to the roadmap. |
| T048 | P1 | M | `CLAUDE.md` (Japanese, stale mirror) → mark stale / align with README. |
| T049 | P1 | B | One "symptom → first tool" decision-tree doc (dedupe `human-workflow.md` + recipes). |
| T050 | P0 | M | This roadmap (create + link from README/AGENTS). |

### repo-level `.kilo` / harness skills (advanced workflows)
| ID | P | Repo | Task |
|---|---|---|---|
| T051 | P1 | M | `renderdoc-capture-analysis` SKILL: audit against current tool count; add `debug_trace_export` + new tools. |
| T052 | P1 | M | `renderdoc-shader-fix` SKILL: verify it references the closed loop + golden edges. |
| T053 | P1 | M | `renderdoc-debug` SKILL: refresh `seed-protocol.json` with `debug_trace_export` + current signatures. |
| T054 | P1 | M | `renderdoc-extension` SKILL: add `debug_trace_export` + Python 3.6-boundary reminders. |
| T055 | P1 | M | `renderdoc-interactive-visualizer` SKILL: generic state-timeline trace template. |
| T056 | P1 | M | `renderdoc-algorithm-article` SKILL: a `debug_trace_export` figure recipe (step→variable heatmap). |

### Distribution & packaging
| ID | P | Repo | Task |
|---|---|---|---|
| T057 | P1 | M | Wheel `packages` must include `mcp_server` + `rdc_harness`; add a build smoke test. |
| T058 | P1 | M | `install_extension.py` idempotent + reinstall-from-clean test (copy → hash-compare → restore). |
| T059 | P1 | M | PyPI metadata (long description, entry-point smoke); dry-run `uv build`. |
| T060 | P2 | S | Package the skill for a marketplace / `$AGENTS_SKILLS` install path. |
| T061 | P1 | M | `.gitignore` for `__pycache__`/`*.pyc`; drop committed `.pyc` from tree. |
| T062 | P1 | M | `RENDERDOC_MCP_CACHE_BACKEND=openviking` optional backend: docs note + graceful-fallback test. |

### Capture-side
| ID | P | Repo | Task |
|---|---|---|---|
| T063 | P1 | S | `capture_webgpu.py`: document `rdc doctor` + a real Chrome Canary run; verify `ddgi_probeData`/`ddgi_rayDir` resources. |
| T064 | P1 | S | Port the UE live-capture recipe (`ue-renderdoc-auto-capture`) into a repo doc + verify. |
| T065 | P1 | S | WebGL recipe regression note: confirm `--in-process-gpu` still works on latest Chromium. |
| T066 | P2 | B | One `capture` front-end that drives both rdc-cli and the MCP bridge (unify the capture entry). |
| T067 | P1 | S | `capture_frame.py` example: update to current API (`SetFrameEvent` before `GetTextureData`). |

### Performance / token efficiency
| ID | P | Repo | Task |
|---|---|---|---|
| T068 | P1 | M | Per-tool token-cost audit; add a max-returned-rows cap for `list_resources`/`get_draw_calls`. |
| T069 | P1 | M | Cache-hit telemetry endpoint (`RENDERDOC_MCP_CACHE_STATS`). |
| T070 | P1 | M | Early-stop in `rdc_harness`: short-circuit a L1 scan on the first hard red-flag (configurable). |
| T071 | P1 | M | Reverse-lookup precompute: lazily index shader→draws / texture→draws per capture instead of full scan each call. |
| T072 | P2 | M | Memoize `SetFrameEvent` state across a session to avoid repeated replays. |

### Cross-repo integration / orchestration
| ID | P | Repo | Task |
|---|---|---|---|
| T073 | P1 | B | Reconcile the two `mcp_server` impls (S wraps rdc-cli; M is the real bridge) — document which is canonical. |
| T074 | P1 | B | Refresh `RenderDocMCP.code-workspace` to include new docs dirs. |
| T075 | P1 | B | Sync `.claude/skills` + `.kilo/skills` wording so both harnesses expose the same renderdoc capability set. |
| T076 | P2 | B | A single parent `AGENTS.md` tying the two repos together. |
| T077 | P1 | B | Populate OpenWolf `cerebrum`/`decision-log` from JOURNEY learnings so OpenWolf is actually useful. |
| T078 | P2 | M | A top-level Hermes `renderdoc-agent` skill mirroring the `.kilo` ones into the hermes skill library. |

### Competitive / research
| ID | P | Repo | Task |
|---|---|---|---|
| T079 | P1 | B | PIX/Nsight comparison: borrow-worthy capabilities (event markers, RS tracking) → a gap doc. |
| T080 | P1 | M | Scripted benchmark: human-loop vs MCP-loop on a real `.rdc` task (wall-clock + tokens). |
| T081 | P2 | B | Publish a "agent vs human GPU debugging" benchmark article (Zhihu). |
| T082 | P2 | M | Research what RenderDoc offers natively for A/B diff vs what we must build. |
| T083 | P1 | M | Close the `debug_trace_export` live-GPU validation and publish the numbers (steps, MB). |

### Robustness / edge cases
| ID | P | Repo | Task |
|---|---|---|---|
| T084 | P1 | M | Markerless/degenerate capture: `get_draw_calls` returns a sane summary, not an error. |
| T085 | P1 | M | HDR/NaN textures: `get_texture_stats` format-aware (NaN/Inf flags); test. |
| T086 | P1 | M | Huge capture: `get_section` >4 MiB refuses gracefully; `list_resources` caps. |
| T087 | P1 | M | Dead-bridge detection (heartbeat) → clear error, not a hang. |
| T088 | P1 | M | Concurrency: two agents one bridge — guard interleaved requests (lock + session isolation). |
| T089 | P0 | M | `resolve_export_path`: ensure export dir exists + unique filename on collision; GPU-free test. |

### Security
| ID | P | Repo | Task |
|---|---|---|---|
| T090 | P1 | M | `resolve_export_path` prevents path-escape from an agent-supplied path (stay under `%TEMP%`). |
| T091 | P1 | M | IPC boundary: `request.json`/`response.json` size cap + reject oversized/foreign requests. |
| T092 | P1 | M | Console passthrough (if built): sandbox + token cap + allowlist. |
| T093 | P1 | M | `compile_shader` with a pathological source must not hang the bridge (timeout). |

### Repo hygiene / infra
| ID | P | Repo | Task |
|---|---|---|---|
| T094 | P0 | M | `.gitignore`: `__pycache__`, `.pyc`, harness scaffolding (`.codex`/`.cursor`/`.opencode`/`.claude`/`.kilo`) unless deliberately tracked. |
| T095 | P0 | M | Remove committed `.pyc` / `__pycache__` from the tree; keep repo clean. |
| T096 | P1 | M | Git attributes: settle LF vs CRLF (the current warnings) via `.gitattributes`. |
| T097 | P1 | M | `renderdoc_extension` version + CHANGELOG entries per release. |
| T098 | P1 | M | CI smoke: install copy → assert files hash-match repo (drift detection). |
| T099 | P2 | M | Vendor a tiny D3D + GL sample `.rdc` for CI so extension paths are executable in tests. |
| T100 | P2 | B | Hardware matrix doc: capture/debug support per RenderDoc version per API. |

---

## P0 detailed plan (reviewed against source anchors)

**P0 = the debug/debug-trace core to full parity + verification-engine micro-hardening + repo hygiene + doc sync.**
All GPU-free, all test-backed, committed **locally** (no remote push — requires explicit authorization).
Deferred to P1/P2: live-GPU validation (T005/T083), A/B diff (T018/T026), API Inspector (T023),
Statistics top-N (T025), capture front-end (T066), CI server (T039), skill packaging (T060).

### Scope (P0)
1. **debug_trace_export → full parity (VS + compute).** Add a `mode`/`kind` parameter (default `pixel`,
   backward-compatible; `vertex` uses `vertex_id`/`instance`/`index`; `compute` uses `group_*`+`thread_*`),
   route through ONE shared `walk()` helper (dedupe the `ContinueDebug`/`FreeTrace`/limit logic). GPU-free
   tests for the walk/serialize/write/limit + handler + bridge timeout + dispatch.
2. **Debug/verification micro-fixes.** `final_variables` var-name fallback (T003); dead import removal (T004);
   `score_from_report` sentinel comment+test (T011); `check_binding_completeness` docstring (T012);
   `rule_setpass_rt` missing-data (T013); `bandwidth`/`min_lod` guard (T014).
3. **Repro guards.** `byte-vs-path` contract test (T035); forbid-`rid.id` and `GetCaptureFile` via
   `pick_capture_access` grep guards (T029/T030); lint/`py_compile` gate (T019); test-all runner (T041).
4. **Hardening.** `resolve_export_path` dir-exists + unique-name (T089); `.gitignore` + drop `.pyc` (T094/T095).
5. **Docs.** Sync `renderdoc-human-experience.md` (T045); README/AGENTS for `debug_trace_export` + status
   (T046); JOURNEY (T047); this roadmap (T050/T028).
6. **Commit.** Commit the dangling, already-green `debug_trace_export` pixel work first, then the new P0 work,
   both as local commits (no push).

### NOT in P0 (off-limits this round)
- Any live-GPU / RenderDoc-GUI verification (no GPU on this host).
- A/B capture diff, API Inspector, Statistics top-N, capture front-end, CI server, PyPI publish, skill market packaging.
- Any `renderdoc_extension` **runtime** behavior that can't be proven GPU-free (real `DebugPixel`/`DebugVertex`/`DebugThread` calls).
- Remote push (explicit authorization required).

### Acceptance criteria (write-down, restated in report)
1. `python3 -m unittest discover -s tests` → **all green**, count ≥ 170 (was 170 at baseline).
2. `py_compile` clean on all `mcp_server`/`rdc_harness` modules and a Python 3.6-compatible parse of every `renderdoc_extension` module.
3. `debug_trace_export` accepts `kind=vertex` and `kind=compute`, shares one walk helper, and is unit-tested GPU-free.
4. `final_variables` returns names on backends where `changes[].after.name` is empty (GL path) — test present.
5. Dead import `Parsers` removed from `debug_service.py`; no other dead-import/NFC regression in the lint gate.
6. `resolve_export_path` creates missing parent dirs and does not collide (unique suffix on reuse).
7. `.gitignore` covers `__pycache__`/`.pyc`; no `.pyc`/`__pycache__` remain tracked.
8. `renderdoc-human-experience.md` is identical across both repos (canonicalized).
9. Local commits created for (a) the pre-existing `debug_trace_export` pixel feature and (b) this P0 slice. No push.

### Self-review rounds
- One fresh-context critic subagent on THIS P0 plan (source-anchored-design): repeat until `blocking = 0`.
- One critic round on the implementation diff before committing (fresh context), apply minimal fixes, repeat until `blocking = 0`.
- Hard cap: 2 critic rounds each.

### Per-round gate for the exec round (answered in the final report)
1. **Success/fail criteria** = the 9 acceptance bars above.
2. **Touch / not-touch** = scope + off-limits above.
3. **Report format** = the fixed round-report block.
4. **Self-review + next** = critic rounds as above; next = wait-for-user after P0 (this session does P0 only).

---

## P0 execution status (2026-09-01)

Done (committed locally this round):
- **T001/T002/T007** — `debug_trace_export` now has `_vertex` + `_compute` full-trajectory entries, sharing a single `_drain`/`_export_trace` walk (was pixel-only). Wired bridge → facade → handler → server, 120s timeout tier.
- **T003** — `final_variables` var-name fallback to the *before* variant when `after.name` is empty (GL). Test.
- **T004** — dead `from ..utils import Parsers` import removed from `debug_service.py`.
- **T012** — `check_binding_completeness` docstring aligned with its actual check.
- **T013/T014** — pinning tests pinning `rule_setpass_rt` / `rule_bandwidth` / `check_min_lod` missing-data guards (what was already guarded is now pinned, no false-PASS).
- **T019/T041/T042** — `scripts/test_all.py` (py_compile + Py3.6 gate + full suite) + `scripts/six_gate.py` + `tests/test_six_gate.py` + VS/compute walk/serialize tests.
- **T035** — export byte-vs-path contract test (`TestExportContractNoBytes`).
- **T045** — verified `renderdoc-human-experience.md` byte-identical across repos (no-op, nothing to do; already canonical).
- **T050** — this roadmap.

Verified no-ops (already satisfied, NOT re-churned):
- `debug_trace_export` pixel feature — already committed (`aba6f86`); working tree was clean; no dangling commit.
- T011 — `score_from_report` 1.0 sentinel already commented + tested (`test_behavioral.py`).
- T089 — `resolve_export_path` dir creation already handled at caller layer (`export_service.py`, `write_trace_file`) + tested (`test_write_tools.py`).
- T094/T095 — `.gitignore` already ignores `__pycache__`/`*.pyc`; none tracked.

Blocked (needs user consent — not retried per gate):
- **T046 (partial)** — `AGENTS.md` is a protected agent-instruction file; the write was consent-gated and timed out. The `test_all` command line landed on disk; the `debug_trace_export` architecture bullet was **not** added. Left uncommitted for review.

Deferred (off-limits this round, moved to P1/P2): live-GPU validation (T005/T083), A/B diff (T018/T026), API Inspector (T023), Statistics top-N (T025), capture front-end (T066), CI server (T039), PyPI publish (T059), skill marketplace (T060), `AGENTS.md` note (T046).

Baseline → after: test count **170 → 194**; `scripts/test_all.py` gate green on `python3 -m unittest discover -s tests`.
