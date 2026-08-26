# AGENTS.md

RenderDoc MCP server: an AI client talks to an MCP server process, which talks over file-based IPC to a Python extension running inside RenderDoc's embedded interpreter. Plus `rdc_harness`, a pure-Python (no GPU) shader edit/replay/verification orchestration library.

## Agent skills

Reusable workflows for this repo live in `.kilo/skills/`:

- `renderdoc-capture-analysis` — token-efficient capture inspection and reverse lookups.
- `renderdoc-shader-fix` — closed-loop shader edit/replace/replay/verify.
- `renderdoc-extension` — safely modify the RenderDoc Python 3.6 extension.
- `renderdoc-debug` — living debug protocol (seed at `seed-protocol.json`).
- `renderdoc-interactive-visualizer` — single-file interactive HTML visualization of an algorithm from a capture (real data + concept + pan/zoom).

Use these skills for multi-step RenderDoc work; use direct tool calls only for one-off reads.

## Commands

```bash
# Tests — stdlib unittest only, no pytest, no lint/typecheck/CI config exists
python -m unittest discover -s tests                    # full suite (fast, no GPU needed)
python -m unittest discover -s tests -p test_rules.py   # single file (tests/ has no __init__.py)

# Harness CLI (Layer-1 deterministic verification on a saved frame summary)
python -m rdc_harness frame.json [--compact]            # or '-' to read JSON from stdin

# Install the RenderDoc extension (copies renderdoc_extension/ into
# %APPDATA%/qrenderdoc/extensions/renderdoc_mcp_bridge, then restart RenderDoc
# and enable it under Tools > Manage Extensions)
python scripts/install_extension.py
```

Packaging is uv-managed (`uv.lock`, `[tool.uv] package = true`); console script `renderdoc-mcp` → `mcp_server.server:main`. The wheel ships **only** `mcp_server` + `rdc_harness` — `renderdoc_extension/` is deployed by copy via the install script, never packaged.

## Hard boundary: two incompatible Pythons

- `mcp_server/` and `rdc_harness/` run on Python ≥ 3.10 (FastMCP 2.x, pydantic 2, modern type annotations).
- `renderdoc_extension/` runs on RenderDoc's **embedded Python 3.6 — stdlib only**. No third-party imports, no post-3.6 syntax. Never import `rdc_harness` or `mcp_server` from extension code; its interpreter cannot parse them.

## Architecture facts that aren't obvious

- IPC is **file-based** (`%TEMP%/renderdoc_mcp/`: `request.json` / `response.json` / `lock`, 100 ms polling on the RenderDoc side) because RenderDoc's embedded Python has no `socket`/`QtNetwork`. Don't "fix" this to sockets.
- All `ReplayController` access on the extension side must go through `BlockInvoke` (see `renderdoc_facade.py`).
- `rdc_harness` orchestration (`orchestrator.iterate_shader_fix`) is decoupled from RenderDoc via the `ShaderBackend`/`ShaderPatcher` protocols so it stays unit-testable without a GPU; `renderdoc_backend.RenderDocShaderBackend` is the only adapter that touches the MCP bridge. Keep that seam when extending.
- WebGPU (D3D12 backend) captures are inspectable as ordinary D3D12 captures; shader source is Dawn's WGSL→HLSL lowering, not WGSL.
- Human 90% toolkit (sibling `renderdoc-skill/renderdoc-human-experience.md`): `pick_pixel`, `get_pixel_history`, `get_mesh_data`, `get_resource_usage`, plus `get_pipeline_state` rasterizer/depth/blend. Unity Editor captures use `get_draw_calls(preset="unity_game_rendering")`. Do not start visual debug with a full `get_texture_data`.
- Response caching (`mcp_server/cache.py`) wraps the bridge on the MCP side. It read-through caches deterministic read tools, bypasses queue-draining/export/debug tools, and invalidates on mutating tools. Cache keys are scoped by capture identity (`get_capture_status().filename` + stat). Backend is in-memory by default; `RENDERDOC_MCP_CACHE_BACKEND=openviking` persists entries under `viking://resources/renderdoc-mcp-cache/` via the optional `openviking_sdk`. Never import cache code from `renderdoc_extension/` (Python 3.6 boundary). See `docs/openviking-cache-design.md`.

## Documentation

- `README.md` (Chinese) is the authoritative, up-to-date doc — it covers `rdc_harness`, the shader edit/replay tools, and the L1/L2 verification design.
- `CLAUDE.md` (Japanese) is an older mirror that predates `rdc_harness`; treat it as stale and prefer the README when they disagree. `JOURNEY.md` is a dev log, not a spec.
