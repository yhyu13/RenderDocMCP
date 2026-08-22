"""
RenderDoc Bridge Client
Communicates with the RenderDoc extension via file-based IPC.
"""

import json
import os
import tempfile
import time
import uuid
from typing import Any


# IPC directory (must match renderdoc_extension/socket_server.py)
IPC_DIR = os.path.join(tempfile.gettempdir(), "renderdoc_mcp")
REQUEST_FILE = os.path.join(IPC_DIR, "request.json")
RESPONSE_FILE = os.path.join(IPC_DIR, "response.json")
LOCK_FILE = os.path.join(IPC_DIR, "lock")


class RenderDocBridgeError(Exception):
    """Error communicating with RenderDoc bridge"""

    pass


# Shader-step debug can exceed the default 30s file-IPC wait.
DEBUG_METHODS = frozenset({"debug_pixel", "debug_vertex", "debug_thread"})
DEBUG_TIMEOUT = 120.0
DEFAULT_TIMEOUT = 30.0


class RenderDocBridge:
    """Client for communicating with RenderDoc extension via file-based IPC"""

    def __init__(self, host: str = "127.0.0.1", port: int = 19876):
        # host/port are kept for API compatibility but not used
        self.host = host
        self.port = port
        self.timeout = DEFAULT_TIMEOUT

    def timeout_for(self, method: str, timeout: float | None = None) -> float:
        if timeout is not None:
            return float(timeout)
        if method in DEBUG_METHODS:
            return DEBUG_TIMEOUT
        return self.timeout

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Call a method on the RenderDoc extension"""
        # Check if IPC directory exists
        if not os.path.exists(IPC_DIR):
            raise RenderDocBridgeError(
                f"Cannot connect to RenderDoc MCP Bridge at {self.host}:{self.port}. "
                "Make sure RenderDoc is running with the MCP Bridge extension loaded."
            )

        request = {
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
        }

        try:
            # Clean up any stale response file
            if os.path.exists(RESPONSE_FILE):
                os.remove(RESPONSE_FILE)

            # Create lock file to signal we're writing
            with open(LOCK_FILE, "w") as f:
                f.write("lock")

            # Write request
            with open(REQUEST_FILE, "w", encoding="utf-8") as f:
                json.dump(request, f)

            # Remove lock file to signal write complete
            os.remove(LOCK_FILE)

            # Wait for response
            start_time = time.time()
            wait = self.timeout_for(method, timeout)
            while True:
                if os.path.exists(RESPONSE_FILE):
                    # Small delay to ensure file is fully written
                    time.sleep(0.01)

                    # Read response
                    with open(RESPONSE_FILE, "r", encoding="utf-8") as f:
                        response = json.load(f)

                    # Clean up response file
                    os.remove(RESPONSE_FILE)

                    if "error" in response:
                        error = response["error"]
                        raise RenderDocBridgeError(f"[{error['code']}] {error['message']}")

                    return response.get("result")

                # Check timeout
                if time.time() - start_time > wait:
                    raise RenderDocBridgeError("Request timed out")

                # Poll interval
                time.sleep(0.05)

        except RenderDocBridgeError:
            raise
        except Exception as e:
            raise RenderDocBridgeError(f"Communication error: {e}")
