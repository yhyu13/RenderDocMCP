"""Process-local cache of *real* ResourceId objects returned by RenderDoc.

Cannot live in resource_id.py's GPU-free tests; this is the 3.6-side glue.
Never construct ResourceId() and poke .id — that field is private and stays 0.
"""

from .resource_id import ids_equal, is_null_id, numeric_id


_CACHE = {}


def remember(rid):
    """Keep a live ResourceId so later string lookups can return the same object."""
    if rid is None:
        return rid
    key = str(rid)
    if is_null_id(key):
        return rid
    _CACHE[key] = rid
    try:
        _CACHE[str(numeric_id(key))] = rid
    except Exception:
        pass
    return rid


def lookup_cached(resource_id_str):
    if resource_id_str is None:
        return None
    key = str(resource_id_str)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    try:
        return _CACHE.get(str(numeric_id(key)))
    except Exception:
        return None


def scan_for_id(items, resource_id_str, attr="resourceId"):
    """Return the live ResourceId on the first matching description object."""
    for item in items or []:
        live = getattr(item, attr, None)
        if live is None:
            continue
        if ids_equal(live, resource_id_str):
            remember(live)
            return live
    return None


def resolve_live(controller, ctx, resource_id_str):
    """Resolve a string to a live ResourceId (cache, then textures/buffers/resources)."""
    hit = lookup_cached(resource_id_str)
    if hit is not None:
        return hit
    if controller is not None:
        try:
            found = scan_for_id(controller.GetTextures(), resource_id_str)
            if found is not None:
                return found
        except Exception:
            pass
        try:
            found = scan_for_id(controller.GetBuffers(), resource_id_str)
            if found is not None:
                return found
        except Exception:
            pass
        try:
            found = scan_for_id(controller.GetResources(), resource_id_str)
            if found is not None:
                return found
        except Exception:
            pass
    if ctx is not None:
        try:
            found = scan_for_id(ctx.GetTextures(), resource_id_str)
            if found is not None:
                return found
        except Exception:
            pass
        try:
            found = scan_for_id(ctx.GetBuffers(), resource_id_str)
            if found is not None:
                return found
        except Exception:
            pass
        try:
            found = scan_for_id(ctx.GetResources(), resource_id_str)
            if found is not None:
                return found
        except Exception:
            pass
    return None
