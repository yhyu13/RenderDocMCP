"""Exercise previously live-unproven tools against the open capture.

Uses the production RenderDocBridge. Prints one JSON object per method.
Does not apply shader replacements (would mutate the capture).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from mcp_server.bridge.client import RenderDocBridge, RenderDocBridgeError


def dump(name, result):
    print("===", name, "===")
    print(json.dumps(result, indent=2, default=str)[:4000])
    print()


def main():
    b = RenderDocBridge()
    status = b.call("get_capture_status")
    if not status.get("loaded"):
        print("no capture loaded")
        return 2
    dump("get_capture_status", status)

    calls = []

    def try_call(name, params=None, timeout=None):
        try:
            result = b.call(name, params or {}, timeout=timeout)
            calls.append((name, "ok", result))
            dump(name, result)
        except RenderDocBridgeError as e:
            calls.append((name, "error", str(e)))
            print("===", name, "ERROR ===")
            print(e)
            print()

    try_call("find_draws_by_resource", {"resource_id": "ResourceId::56"})
    try_call("get_resource_usage", {"resource_id": "ResourceId::56"})
    try_call("get_shader_info", {"event_id": 550, "stage": "pixel"})
    try_call("get_thumbnail", {})
    try_call("export_render_target", {"event_id": 550, "dest_type": "png"})
    try_call("export_buffer", {"resource_id": "ResourceId::125"})
    try_call("set_event", {"event_id": 550})
    try_call("get_section", {"name": "notes", "max_bytes": 4096})
    try_call(
        "compile_custom_shader",
        {
            "source": (
                "#version 330\n"
                "layout(binding=0) uniform sampler2D t;\n"
                "out vec4 color;\n"
                "void main(){ color = vec4(1.0); }\n"
            ),
            "stage": "pixel",
            "entry": "main",
            "encoding": "glsl",
        },
        timeout=120,
    )
    try_call("restore_all_replacements", {})

    print("=== SUMMARY ===")
    for name, kind, payload in calls:
        if kind == "ok":
            extra = ""
            if isinstance(payload, dict):
                extra = " keys=" + ",".join(list(payload)[:8])
            print("PASS", name, extra)
        else:
            print("FAIL", name, payload)
    return 0 if all(k == "ok" for _, k, _ in calls) else 1


if __name__ == "__main__":
    sys.exit(main())
