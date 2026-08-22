"""Configuration for RenderDoc MCP Server"""

import os


class Settings:
    """Server settings"""

    def __init__(self):
        self.renderdoc_host = os.environ.get("RENDERDOC_MCP_HOST", "127.0.0.1")
        self.renderdoc_port = int(os.environ.get("RENDERDOC_MCP_PORT", "19876"))
        self.cache_enabled = os.environ.get("RENDERDOC_MCP_CACHE", "1") not in ("0", "false", "False")
        self.cache_backend = os.environ.get("RENDERDOC_MCP_CACHE_BACKEND", "memory").lower()
        self.cache_max_entry_bytes = int(
            os.environ.get("RENDERDOC_MCP_CACHE_MAX_ENTRY_BYTES", str(4 * 1024 * 1024))
        )


settings = Settings()
