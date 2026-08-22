"""GPU-free tests for the MCP-side read-through response cache."""

import json
import os
import tempfile
import types
import unittest

from mcp_server.cache import (
    CACHEABLE_READ_ONLY,
    INVALIDATING_METHODS,
    CacheUnavailable,
    MemoryBackend,
    OpenVikingBackend,
    ResponseCache,
    canonical_params,
    make_cache,
)


class FakeBridge:
    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls = []

    def call(self, method, params=None, timeout=None):
        self.calls.append((method, params))
        if method in self.responses:
            return self.responses[method]
        return {"method": method, "params": params}


def _scope_provider(path):
    def provider():
        return {"loaded": True, "filename": path}

    return provider


class TestCanonicalParams(unittest.TestCase):
    def test_order_independent(self):
        a = canonical_params({"b": 2, "a": [1, 2], "c": None})
        b = canonical_params({"c": None, "a": [1, 2], "b": 2})
        self.assertEqual(a, b)


class TestMemoryBackend(unittest.TestCase):
    def test_roundtrip_and_delete(self):
        backend = MemoryBackend(ttl_seconds=10)
        backend.put("k", "v")
        self.assertEqual(backend.get("k"), "v")
        backend.delete("k")
        self.assertIsNone(backend.get("k"))

    def test_expiry(self):
        backend = MemoryBackend(ttl_seconds=0)
        backend.put("k", "v")
        self.assertIsNone(backend.get("k"))


class TestOpenVikingBackend(unittest.TestCase):
    def _fake_client(self):
        client = types.SimpleNamespace()
        client.made = {}
        client.writes = []
        client.removals = []

        def mkdir(uri):
            return None

        def read_raw(uri):
            return client.made.get(uri)

        def write(uri, value, **kwargs):
            client.made[uri] = value
            client.writes.append((uri, kwargs))

        def rm(uri, **kwargs):
            client.removals.append((uri, kwargs))

        client.mkdir = mkdir
        client.read_raw = read_raw
        client.write = write
        client.rm = rm
        return client

    def test_put_uses_vectors_only(self):
        client = self._fake_client()
        backend = OpenVikingBackend(base_uri="viking://resources/rdc-cache", client=client)
        backend.put("abc", '{"x": 1}')
        self.assertEqual(client.writes[0][1]["processing_mode"], "vectors_only")
        self.assertEqual(client.made["viking://resources/rdc-cache/abc.json"], '{"x": 1}')

    def test_get_roundtrip(self):
        client = self._fake_client()
        backend = OpenVikingBackend(base_uri="viking://resources/rdc-cache", client=client)
        backend.put("abc", "payload")
        self.assertEqual(backend.get("abc"), "payload")

    def test_get_missing_is_none(self):
        client = self._fake_client()
        backend = OpenVikingBackend(base_uri="viking://resources/rdc-cache", client=client)
        self.assertIsNone(backend.get("missing"))

    def test_clear_then_put_recreates_base(self):
        client = self._fake_client()
        backend = OpenVikingBackend(base_uri="viking://resources/rdc-cache", client=client)
        backend.put("abc", "v1")
        backend.clear()
        # After clear the backend must be able to put again (re-mkdir the base).
        backend.put("abc", "v2")
        self.assertEqual(backend.get("abc"), "v2")


class TestResponseCache(unittest.TestCase):
    def _cache(self, bridge, backend=None):
        return ResponseCache(
            bridge,
            backend=backend or MemoryBackend(ttl_seconds=60),
            scope_provider=_scope_provider(self._capture_path),
        )

    def setUp(self):
        fd, self._capture_path = tempfile.mkstemp(suffix=".rdc")
        os.close(fd)

    def tearDown(self):
        try:
            os.remove(self._capture_path)
        except OSError:
            pass

    def test_read_through_caches_and_hits(self):
        bridge = FakeBridge({"get_pipeline_state": {"event_id": 1, "value": "stable"}})
        cache = self._cache(bridge)

        first = cache.call("get_pipeline_state", {"event_id": 1})
        second = cache.call("get_pipeline_state", {"event_id": 1})

        self.assertEqual(first, {"event_id": 1, "value": "stable"})
        self.assertEqual(second, first)
        # The real bridge must be called exactly once for the cached method.
        self.assertEqual(
            sum(1 for c in bridge.calls if c[0] == "get_pipeline_state"),
            1,
        )
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.misses, 1)

    def test_mutation_invalidates(self):
        bridge = FakeBridge({"get_frame_summary": {"n": 1}})
        cache = self._cache(bridge)

        cache.call("get_frame_summary")
        cache.call("replace_shader", {"event_id": 1, "stage": "pixel", "compiled_resource_id": "x"})
        cache.call("get_frame_summary")

        self.assertEqual(
            sum(1 for c in bridge.calls if c[0] == "get_frame_summary"),
            2,
        )

    def test_debug_messages_bypass_and_not_cached(self):
        bridge = FakeBridge({"get_debug_messages": {"messages": ["drain me"]}})
        cache = self._cache(bridge)

        cache.call("get_debug_messages")
        cache.call("get_debug_messages")

        self.assertEqual(
            sum(1 for c in bridge.calls if c[0] == "get_debug_messages"),
            2,
        )

    def test_capture_scope_change_invalidates(self):
        bridge = FakeBridge({"get_pipeline_state": {"event_id": 1}})
        cache = self._cache(bridge)

        cache.call("get_pipeline_state", {"event_id": 1})

        # Change the capture file identity (different path).
        fd, other = tempfile.mkstemp(suffix=".rdc")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(other) and os.remove(other))
        cache._scope_provider = _scope_provider(other)

        cache.call("get_pipeline_state", {"event_id": 1})
        self.assertEqual(
            sum(1 for c in bridge.calls if c[0] == "get_pipeline_state"),
            2,
        )

    def test_no_scope_bypasses(self):
        bridge = FakeBridge({"get_texture_info": {"ok": 1}})
        cache = ResponseCache(
            bridge,
            backend=MemoryBackend(),
            scope_provider=lambda: {"loaded": True, "filename": None},
        )
        cache.call("get_texture_info", {"resource_id": "ResourceId::1"})
        cache.call("get_texture_info", {"resource_id": "ResourceId::1"})
        self.assertEqual(
            sum(1 for c in bridge.calls if c[0] == "get_texture_info"),
            2,
        )

    def test_oversized_entry_not_cached(self):
        big = "x" * (1024 * 1024)
        bridge = FakeBridge({"get_section": {"blob": big}})
        cache = ResponseCache(
            bridge,
            backend=MemoryBackend(ttl_seconds=60),
            max_entry_bytes=1024,
            scope_provider=_scope_provider(self._capture_path),
        )
        cache.call("get_section", {"index": 0})
        cache.call("get_section", {"index": 0})
        self.assertEqual(
            sum(1 for c in bridge.calls if c[0] == "get_section"),
            2,
        )

    def test_unavailable_backend_bypasses(self):
        class BrokenBackend:
            def get(self, key):
                raise CacheUnavailable("down")

            def put(self, key, value):
                raise CacheUnavailable("down")

            def delete(self, key):
                pass

            def clear(self):
                pass

        bridge = FakeBridge({"get_frame_summary": {"ok": 1}})
        cache = ResponseCache(
            bridge,
            backend=BrokenBackend(),
            scope_provider=_scope_provider(self._capture_path),
        )
        result = cache.call("get_frame_summary")
        self.assertEqual(result, {"ok": 1})

    def test_make_cache_falls_back_to_memory(self):
        # Force OpenViking construction failure by not passing use_openviking
        # and just checking the default memory path.
        bridge = FakeBridge()
        cache = make_cache(bridge, use_openviking=False)
        self.assertIsInstance(cache._backend, MemoryBackend)


class TestMethodClassification(unittest.TestCase):
    def test_read_only_and_invalidating_are_disjoint(self):
        self.assertTrue(CACHEABLE_READ_ONLY.isdisjoint(INVALIDATING_METHODS))

    def test_debug_messages_not_cacheable(self):
        self.assertNotIn("get_debug_messages", CACHEABLE_READ_ONLY)
        self.assertNotIn("get_debug_messages", INVALIDATING_METHODS)

    def test_mutators_invalidate(self):
        for method in ("replace_shader", "write_section", "open_capture"):
            self.assertIn(method, INVALIDATING_METHODS)


if __name__ == "__main__":
    unittest.main()
