# OpenViking-backed caching for RenderDoc MCP

## 1. Why OpenViking is useful for caching `renderdoc`

The RenderDoc MCP server (`mcp_server/server.py`) exposes ~60 tools, every one of
which goes through `RenderDocBridge.call(...)`: write `request.json`, poll for
`response.json` at 50 ms, and then run a RenderDoc `BlockInvoke`/GPU operation.
There is currently **no response caching**, so an agent re-asking the same
question ("get the pipeline state at event 7538", "read this texture") pays the
full file-IPC + GPU cost every time.

OpenViking contributes two orthogonal caching layers:

- **`openviking_sdk.SyncHTTPClient`** gives the MCP side a persistent, semantic
  filesystem (`viking://`) with `mkdir` / `write` / `read_raw` / `rm`. That lets
  the server persist cache entries *across process restarts and across agents*
  instead of losing them when the MCP server exits.
- **RAGFS `CachedFileSystem`** (in the OpenViking repo) is the native/Redis/
  Mooncake read-through cache used by OpenViking itself. It is the model for the
  wrapper implemented here: read-through, generation-aware invalidation, hit/miss
  metrics, and a pluggable provider contract.

This change implements a **read-through response cache on the MCP side**. The
default backend is in-process memory (safe, zero dependencies). An optional
`OpenVikingBackend` persists entries under `viking://resources/renderdoc-mcp-cache/`
when an `openviking_sdk` client is available, otherwise it degrades to memory.

## 2. Design

```
MCP tool -> ResponseCache.call(inner_bridge, method, params)
              |
              +-- method not in READ_ONLY? -> inner_bridge (passthrough)
              |      (and if method is MUTATING -> invalidate cache)
              |
              +-- key = sha256(capture_scope + method + canonical_params)
              +-- backend.get(key) -> hit? return cached JSON
              +-- miss? inner_bridge(...) -> backend.put(key, json)
```

### Cache key = capture scope + method + canonical params

Two captures can have identical `event_id` / `ResourceId` strings but different
data, so the key must include capture identity. `get_capture_status()` returns
`filename` (RenderDoc's `GetCaptureFilename`, normally a full path). The scope
provider stats that path and combines `path@mtime_ns@size`. The scope is
memoized briefly to avoid a `get_capture_status` IPC call on every lookup.

### Categories

- `READ_ONLY_METHODS`: deterministic reads (`get_pipeline_state`,
  `get_texture_data`, `get_frame_summary`, `list_resources`, ...). Cached.
- `MUTATING_METHODS`: anything that changes the loaded capture, replacements,
  compiled shaders, debug queue, or sections (`replace_shader`, `write_section`,
  `open_capture`, ...). Bypassed and invalidates the cache after success.
- Everything else (`get_capture_status`, `get_debug_messages`, exports, step
  debuggers): bypassed without invalidating. `get_debug_messages` drains a queue
  so it must never be cached; exports write files but do not mutate the capture.

### Backends

- `MemoryBackend`: thread-safe dict with per-entry TTL, entry count cap, and
  per-value byte cap. Default.
- `OpenVikingBackend`: lazily imports `openviking_sdk.SyncHTTPClient`; stores one
  JSON file per entry under `viking://resources/renderdoc-mcp-cache/<key>.json`.
  Uses `write(processing_mode="vectors_only")` / `read_raw` / `rm`. Any import or
  config error is surfaced as `unavailable` and the cache transparently bypasses.

Values are always stored as JSON text, which is safe because the bridge already
returns JSON-native values (dict/list/str/int/float/bool/None).

## 3. Self-critique (before implementation) and the fixes applied

| # | Risk / objection | Resolution |
|---|---|---|
| 1 | Caching by `event_id`/`ResourceId` alone is wrong across captures. | Key includes `path@mtime_ns@size` capture scope. |
| 2 | `replace_shader` / `replace_resource` change read-tool results -> stale reads. | Any `MUTATING_METHODS` call invalidates the whole current cache. |
| 3 | `get_debug_messages` drains its queue; caching would replay stale messages. | Excluded from cacheable set. |
| 4 | `get_capture_status` used for scope would recurse / self-invalidate. | It is bypass-only, never cached, never invalidates. |
| 5 | OpenViking SDK may not be installed in this environment. | Lazy import; backend reports `unavailable` and falls back to memory. |
| 6 | OpenViking default write does semantic processing (wasteful for cache blobs). | Use `processing_mode="vectors_only"`; read back with `read_raw`. |
| 7 | Huge `get_section`/`get_texture_data` results could balloon memory/OpenViking. | `max_entry_bytes` cap skips caching over-limit results. |
| 8 | Testing must stay GPU-free and not import FastMCP. | Cache module is standalone; tests use a fake bridge + fake backend. |
| 9 | Thread safety: FastMCP may call tools concurrently. | MemoryBackend uses a lock; ResponseCache keeps no shared mutable scope state except a locked memo. |

## 4. Verification plan

- New `tests/test_cache.py` (stdlib `unittest`, no GPU, no FastMCP import):
  key stability, read-through hit/miss, mutation invalidation, capture-scope
  change, `get_debug_messages` bypass, entry-size cap, OpenViking backend with a
  mocked `openviking_sdk` module.
- Full suite: `py -3.13 -m unittest discover -s tests` (baseline 136/136, expect
  more with the new file).

## 5. Non-goals

- No caching of exports (`export_texture` writes a file; return the path).
- No caching of step-debuggers (`debug_pixel/vertex/thread`) or `replay_event`.
- No attempt to make the RenderDoc extension side (Python 3.6, stdlib only)
  depend on OpenViking; caching lives on the MCP side (Python >= 3.10).
