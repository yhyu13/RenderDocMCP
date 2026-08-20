---
name: renderdoc-extension
description: Work safely inside the RenderDoc Python extension. Use when modifying renderdoc_extension/, installing the extension, or debugging the file-IPC bridge.
---

# RenderDoc Extension Skill

## When to use

- You need to add, change, or fix a RenderDoc MCP bridge request handler.
- You are installing or updating the extension in qrenderdoc.
- You are debugging why the bridge does not respond (file IPC, BlockInvoke, etc.).

## When NOT to use

- You are writing AI/MCP-side code (`mcp_server/` or `rdc_harness/`).
- You want to change the IPC mechanism.
- You need third-party libraries inside RenderDoc's embedded interpreter.

## Hard boundary: two incompatible Pythons

| Side | Python version | Allowed imports |
|------|----------------|-----------------|
| `mcp_server/`, `rdc_harness/` | ≥ 3.10 | Anything in `pyproject.toml` (FastMCP, pydantic, etc.) |
| `renderdoc_extension/` | 3.6 (RenderDoc embedded) | **stdlib only** |

- Never import `rdc_harness` or `mcp_server` from extension code.
- Never use syntax newer than Python 3.6 (e.g. assignment expressions, positional-only args).
- Never use `socket`, `QtNetwork`, or async networking.

## Architecture facts

- **IPC is file-based**: `%TEMP%/renderdoc_mcp/request.json`, `response.json`, `lock`.
- RenderDoc polls the request file every ~100 ms.
- All `ReplayController` access must go through `BlockInvoke` (`renderdoc_facade._invoke`).
- Services live under `renderdoc_extension/services/` and are wired in `RenderDocFacade`.

## Adding a new bridge method

1. Implement the operation in the correct service under `renderdoc_extension/services/`.
2. Expose it through `RenderDocFacade` in `renderdoc_facade.py`.
3. Add handler `_handle_<method>` in `request_handler.py` and register it in `self._methods`.
4. Add the corresponding `@mcp.tool` in `mcp_server/server.py`.
5. Add a test that exercises the handler through the facade or a fake facade.

## Installing the extension

```bash
python scripts/install_extension.py
```

Then restart RenderDoc and enable the extension under **Tools > Manage Extensions**.

## Common pitfalls

| Pitfall | Why it breaks | Correct approach |
|---------|---------------|------------------|
| Using `socket` in the extension | Embedded Python lacks `socket` | Keep file-based IPC |
| Modern type annotations in extension code | Python 3.6 cannot parse them | Use plain docstrings/comments, or no annotations |
| Calling RenderDoc API directly from a thread | Most API calls must be on the replay thread | Use `BlockInvoke` via `renderdoc_facade` |
| Importing `rdc_harness` from extension | Pulls Python 3.10+ syntax and pydantic | Duplicate only the tiny data shapes you need, or pass raw dicts |

## Debugging the bridge

1. Confirm the IPC directory exists: `%TEMP%/renderdoc_mcp/`.
2. Check that `request.json` is being written and `lock` is removed by the client.
3. Look at RenderDoc's **Python Console** / stderr for extension traceback output.
4. Use `ping` from the MCP server to verify round-trip communication.
