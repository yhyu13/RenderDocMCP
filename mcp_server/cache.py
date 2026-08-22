"""Read-through response cache for the RenderDoc MCP server.

The MCP server normally sends every tool call across file-based IPC into
RenderDoc and runs GPU/replay work.  This module wraps that bridge so that
deterministic, read-only tool results are cached, while mutating calls bypass
the cache and invalidate it.

Two backends are provided:

* :class:`MemoryBackend` -- in-process, thread-safe, zero-dependency.
* :class:`OpenVikingBackend` -- persists entries under a ``viking://`` URI using
  the optional ``openviking_sdk`` package.  If the SDK is not installed or the
  server is unreachable, the backend reports itself unavailable and the cache
  transparently falls back to memory.

The cache deliberately lives on the MCP side (standard Python >= 3.10), never
inside ``renderdoc_extension/`` (RenderDoc's embedded Python 3.6).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any, Callable, Dict, Optional, Protocol


class Bridge(Protocol):
    """Minimal shape of :class:`mcp_server.bridge.client.RenderDocBridge`."""

    def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any: ...


# Deterministic, capture-relative reads that are safe to cache.
CACHEABLE_READ_ONLY = frozenset(
    {
        "get_draw_calls",
        "get_frame_summary",
        "find_draws_by_shader",
        "find_draws_by_texture",
        "find_draws_by_resource",
        "get_draw_call_details",
        "get_action_timings",
        "get_shader_info",
        "get_buffer_contents",
        "get_texture_info",
        "get_texture_data",
        "get_pipeline_state",
        "list_captures",
        "get_shader_source",
        "list_resources",
        "get_resource",
        "get_texture_stats",
        "list_shader_encodings",
        "list_shaders",
        "shader_map",
        "search_shaders",
        "get_counters",
        "get_snapshot",
        "list_sections",
        "get_section",
    }
)

# Calls that change the loaded capture, its replacements, or its sections and
# therefore make previously cached read results stale.
INVALIDATING_METHODS = frozenset(
    {
        "open_capture",
        "close_capture",
        "replace_shader",
        "remove_shader_replacement",
        "replay_event",
        "replace_resource",
        "restore_resource",
        "restore_all_replacements",
        "write_section",
        "embed_dependencies",
        "remove_dependencies",
    }
)


class CacheUnavailable(RuntimeError):
    """Raised by a backend when it cannot serve requests."""


def canonical_params(params: Optional[Dict[str, Any]]) -> str:
    """Return a stable JSON representation of ``params`` for cache keys."""
    return json.dumps(
        params or {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=repr,
    )


def _now() -> float:
    return time.monotonic()


class CacheBackend(Protocol):
    """String-in / string-out cache backend contract."""

    def get(self, key: str) -> Optional[str]: ...

    def put(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def clear(self) -> None: ...


class MemoryBackend:
    """Thread-safe in-process cache with TTL and simple capacity limits."""

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        max_entries: int = 512,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Dict[str, tuple[str, float]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            item = self._entries.get(key)
            if item is None:
                self.misses += 1
                return None
            value, expires_at = item
            if expires_at <= _now():
                del self._entries[key]
                self.misses += 1
                return None
            # Refresh on read (simple LRU-ish behaviour).
            del self._entries[key]
            self._entries[key] = (value, expires_at)
            self.hits += 1
            return value

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._entries[key] = (value, _now() + self._ttl)
            while len(self._entries) > self._max_entries:
                oldest = next(iter(self._entries))
                del self._entries[oldest]

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class OpenVikingBackend:
    """Persist cache entries under a ``viking://`` resource tree.

    ``openviking_sdk`` is imported lazily so the RenderDoc MCP package does not
    gain a hard dependency on OpenViking.  Values are written with
    ``processing_mode="vectors_only"`` because they are opaque JSON blobs that do
    not benefit from semantic extraction.
    """

    def __init__(
        self,
        base_uri: str = "viking://resources/renderdoc-mcp-cache",
        client: Any = None,
    ) -> None:
        self._base_uri = base_uri.rstrip("/")
        self._client = client
        self._ready = False
        self._ensure_error: Optional[str] = None
        self._ensure_lock = threading.Lock()

    def _load_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import openviking_sdk  # type: ignore
        except Exception as exc:  # pragma: no cover - import path is environment specific
            raise CacheUnavailable("openviking_sdk is not installed: %s" % exc) from exc
        try:
            self._client = openviking_sdk.SyncHTTPClient()
        except Exception as exc:  # pragma: no cover - depends on local ov config
            raise CacheUnavailable("could not build OpenViking client: %s" % exc) from exc
        return self._client

    def _ensure_base(self, client: Any) -> None:
        with self._ensure_lock:
            if self._ready:
                return
            if self._ensure_error:
                raise CacheUnavailable(self._ensure_error)
            try:
                try:
                    client.mkdir(self._base_uri)
                except Exception:
                    # Directory may already exist; existence is not fatal.
                    pass
                self._ready = True
            except Exception as exc:  # pragma: no cover - network/remote error
                self._ensure_error = "OpenViking backend unavailable: %s" % exc
                raise CacheUnavailable(self._ensure_error) from exc

    def _uri(self, key: str) -> str:
        return "%s/%s.json" % (self._base_uri, key)

    def get(self, key: str) -> Optional[str]:
        client = self._load_client()
        self._ensure_base(client)
        try:
            return client.read_raw(self._uri(key))
        except Exception:
            # A missing key is the normal cache-miss path; swallow it.
            return None

    def put(self, key: str, value: str) -> None:
        client = self._load_client()
        self._ensure_base(client)
        try:
            client.write(
                self._uri(key),
                value,
                mode="replace",
                wait=False,
                processing_mode="vectors_only",
            )
        except Exception as exc:  # pragma: no cover - network/remote error
            raise CacheUnavailable("OpenViking write failed: %s" % exc) from exc

    def delete(self, key: str) -> None:
        client = self._load_client()
        try:
            client.rm(self._uri(key), recursive=False)
        except Exception:
            # Missing key is a no-op.
            return

    def clear(self) -> None:
        client = self._load_client()
        try:
            client.rm(self._base_uri, recursive=True)
        except Exception:
            return
        finally:
            with self._ensure_lock:
                self._ready = False
                self._ensure_error = None


def _scope_from_status(status: Any) -> Optional[str]:
    """Derive a capture identity from ``get_capture_status`` output."""
    if not isinstance(status, dict):
        return None
    if not status.get("loaded"):
        return "unloaded"
    path = status.get("filename")
    if not path or not os.path.isfile(path):
        return None
    try:
        st = os.stat(path)
        return "%s@%d@%d" % (path, st.st_mtime_ns, st.st_size)
    except OSError:
        return None


class ResponseCache:
    """Wrap a RenderDoc bridge with read-through, capture-scoped caching."""

    def __init__(
        self,
        inner: Bridge,
        backend: Optional[CacheBackend] = None,
        max_entry_bytes: int = 4 * 1024 * 1024,
        scope_provider: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._inner = inner
        self._backend = backend if backend is not None else MemoryBackend()
        self._max_entry_bytes = max_entry_bytes
        self._scope_provider = scope_provider or self._default_scope
        self.hits = 0
        self.misses = 0
        self.bypasses = 0

    def _default_scope(self) -> Any:
        return self._inner.call("get_capture_status")

    def _current_scope(self) -> Optional[str]:
        # Derived on every call from the cheap get_capture_status round-trip.
        # This keeps the key correct even if a capture is opened/closed outside
        # the MCP bridge (e.g. directly in the RenderDoc UI).
        return _scope_from_status(self._scope_provider())

    def _key(self, method: str, params: Optional[Dict[str, Any]]) -> Optional[str]:
        scope = self._current_scope()
        if scope is None:
            return None
        digest = hashlib.sha256()
        digest.update(scope.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(method.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(canonical_params(params).encode("utf-8"))
        return digest.hexdigest()

    def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        if method in INVALIDATING_METHODS:
            result = self._inner.call(method, params, timeout)
            try:
                self._backend.clear()
            except Exception:
                pass
            return result

        if method not in CACHEABLE_READ_ONLY:
            self.bypasses += 1
            return self._inner.call(method, params, timeout)

        key = self._key(method, params)
        if key is None:
            # No reliable capture scope: do not risk serving the wrong data.
            self.bypasses += 1
            return self._inner.call(method, params, timeout)

        try:
            cached = self._backend.get(key)
        except CacheUnavailable:
            self.bypasses += 1
            return self._inner.call(method, params, timeout)

        if cached is not None:
            self.hits += 1
            return json.loads(cached)

        self.misses += 1
        result = self._inner.call(method, params, timeout)
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if len(encoded.encode("utf-8")) <= self._max_entry_bytes:
            try:
                self._backend.put(key, encoded)
            except CacheUnavailable:
                # Backend failure is not fatal to the actual tool call.
                pass
        return result

    def flush(self) -> None:
        """Drop all cached entries."""
        try:
            self._backend.clear()
        except Exception:
            pass


def make_cache(inner: Bridge, *, use_openviking: bool = False) -> ResponseCache:
    """Create a :class:`ResponseCache` with the requested backend.

    ``use_openviking`` is a hint.  If the OpenViking backend cannot be built, the
    cache transparently falls back to in-memory storage so the MCP server never
    fails to start because of an unavailable cache.
    """

    backend: CacheBackend = MemoryBackend()
    if use_openviking:
        try:
            backend = OpenVikingBackend()
        except CacheUnavailable:
            backend = MemoryBackend()
    return ResponseCache(inner, backend=backend)
