"""Ping the running RenderDoc MCP bridge over file IPC.

Uses the production bridge client (mcp_server.bridge.client) so this exercises
the exact path the MCP server takes. Exit code 0 = bridge answered.

Usage:
    py -3.13 scripts/ping_bridge.py            # ping only, print status
    py -3.13 scripts/ping_bridge.py --summary  # also print frame summary
"""
import json
import sys

from mcp_server.bridge.client import RenderDocBridge, RenderDocBridgeError


def main(argv):
    want_summary = "--summary" in argv
    b = RenderDocBridge()
    try:
        status = b.call("get_capture_status")
    except RenderDocBridgeError as e:
        print("BRIDGE ERROR:", e)
        return 1

    print("BRIDGE OK")
    print(json.dumps(status, indent=2, default=str))

    if not status.get("loaded"):
        print("WARNING: bridge answered but no capture is loaded in RenderDoc.")
        return 2

    if want_summary:
        try:
            summary = b.call("get_frame_summary")
            print("FRAME SUMMARY OK")
            print(json.dumps(summary, indent=2, default=str)[:4000])
        except RenderDocBridgeError as e:
            print("SUMMARY ERROR:", e)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
