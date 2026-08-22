"""GPU-free helpers for GetMinMax / GetHistogram JSON. Python 3.6, no renderdoc.

get_texture_stats must never scan texture bytes in Python. These helpers only
reshape PixelValue-like objects and downsample histogram buckets.
"""

HISTOGRAM_OUT_BUCKETS = 16


def _seq4(raw):
    if raw is None:
        return None
    try:
        return [raw[i] for i in range(min(4, len(raw)))]
    except Exception:
        try:
            return [raw[0], raw[1], raw[2], raw[3]]
        except Exception:
            return None


def channels_from_pixel(val):
    """Duck-typed PixelValue -> {float, uint, int} (each a 4-list or None)."""
    out = {"float": None, "uint": None, "int": None}
    if val is None:
        return out
    try:
        fv = _seq4(getattr(val, "floatValue", None))
        if fv is not None:
            out["float"] = [float(c) for c in fv]
    except Exception:
        pass
    try:
        uv = _seq4(getattr(val, "uintValue", None))
        if uv is not None:
            out["uint"] = [int(c) for c in uv]
    except Exception:
        pass
    try:
        iv = _seq4(getattr(val, "intValue", None))
        if iv is not None:
            out["int"] = [int(c) for c in iv]
    except Exception:
        pass
    return out


def _is_nan_or_inf(v):
    try:
        if v != v:
            return True
        if v == float("inf") or v == float("-inf"):
            return True
    except Exception:
        return False
    return False


def nan_inf_flags(floats):
    flags = []
    seen = set()
    for v in floats or []:
        token = None
        try:
            if v != v:
                token = "nan"
            elif v == float("inf"):
                token = "+inf"
            elif v == float("-inf"):
                token = "-inf"
        except Exception:
            token = None
        if token and token not in seen:
            seen.add(token)
            flags.append(token)
    return flags


def unique_flags(*groups):
    seen = set()
    out = []
    for group in groups:
        for token in group or []:
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out


def histogram_channels(include_alpha=True):
    return (True, True, True, bool(include_alpha))


def histogram_range(min_floats, max_floats):
    """Return (minval, maxval) for GetHistogram, or None if the range is unusable."""
    lo = list(min_floats or [])
    hi = list(max_floats or [])
    if not lo or not hi:
        return None
    try:
        minval = min(lo)
        maxval = max(hi)
    except Exception:
        return None
    if _is_nan_or_inf(minval) or _is_nan_or_inf(maxval):
        return None
    if minval == maxval:
        return None
    return (float(minval), float(maxval))


def reduce_histogram(buckets, target=HISTOGRAM_OUT_BUCKETS):
    items = list(buckets or [])
    if not items:
        return []
    target = int(target) if target else HISTOGRAM_OUT_BUCKETS
    if target <= 0:
        target = HISTOGRAM_OUT_BUCKETS
    n = len(items)
    if n <= target:
        return [int(x) for x in items]
    out = [0] * target
    for i, v in enumerate(items):
        dest = int(i * target / float(n))
        if dest >= target:
            dest = target - 1
        out[dest] += int(v)
    return out
