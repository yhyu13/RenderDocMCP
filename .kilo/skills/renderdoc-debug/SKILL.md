---
name: renderdoc-debug
description: Repair RenderDoc MCP / rdc_harness failures using a living protocol of error signatures, root causes, and verified fixes.
---

# RenderDoc Debug Skill

## When to use

- The MCP bridge returns an error or times out.
- `compile_shader`, `replace_shader`, or `replay_event` fails.
- A verification layer returns unexpected `FAIL`/`SKIP` results.
- The same failure pattern appears more than once.

## When NOT to use

- The error is a single obvious typo in one file.
- The failure is caused by a missing environment (no RenderDoc, no Python 3.10+).
- The user explicitly asked for a one-off manual fix.

## Core idea: living protocol

Maintain a structured collection of `(signature, root_cause, fix)` entries. Match new failures, apply known fixes, and record verified fixes back into the protocol. Over time, repeated patterns generalize into proactive validation rules.

## Protocol schema

See `.kilo/skills/renderdoc-debug/seed-protocol.json`. A minimal entry:

```json
{
  "id": "entry-bridge-timeout-001",
  "kind": "reactive",
  "signature": {
    "stage": "runtime",
    "errorCode": "RenderDocBridgeError",
    "messagePattern": "Request timed out",
    "fileContext": "mcp_server/bridge/client.py"
  },
  "rootCause": "RenderDoc extension is not loaded or the IPC directory is stale.",
  "tags": ["bridge", "ipc", "timeout"],
  "fix": {
    "type": "shell",
    "description": "Restart RenderDoc with the MCP Bridge extension enabled and clear stale IPC files.",
    "patch": "rm %TEMP%/renderdoc_mcp/request.json %TEMP%/renderdoc_mcp/response.json %TEMP%/renderdoc_mcp/lock"
  },
  "occurrences": 0,
  "contributingProjects": []
}
```

## Debug loop

1. Run proactive checks from the protocol (cheap static / config validations).
2. Reproduce the failing MCP call or harness stage.
3. Parse the error into `errorCode`, `message`, `fileContext`.
4. Match against entries:
   - errorCode weight 0.5
   - message regex weight 0.35
   - file context weight 0.15
   - accept if confidence ≥ 0.8
5. Apply the matched fix; if no match, diagnose with context and apply a minimal targeted edit.
6. Re-run the failing stage.
7. If the fix succeeds, increment `occurrences` and record the project.
8. When an `errorCode` reaches 3 verified occurrences, generalize it into a `ProtocolRule`.

## Fix types

| Type | Payload convention |
|------|-------------------|
| `edit` | `search|||replace` (or unified diff) |
| `config` | JSON patch for `mcp_server/config.py` or env vars |
| `create` | `path::content` |
| `delete` | file path |
| `shell` | command string — **log only, do not auto-execute** |

## Best practices

- Verify before recording: only promote a fix after a successful re-run.
- Prefer minimal edits; do not refactor unrelated code during a debug loop.
- Keep shell commands out of automatic execution.
- Separate cheap static checks from compile/replay-dependent checks.
- Periodically review generalized rules to remove false positives.
