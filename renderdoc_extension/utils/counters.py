"""JSON-safe GPU counter values. Python 3.6 / no renderdoc import."""


def counter_value(value):
    """Flatten ReplayController counter samples to a JSON-safe number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    for attr in ("u64", "d", "f", "u32", "i64", "i32"):
        try:
            v = getattr(value, attr)
        except Exception:
            v = None
        if v is not None:
            try:
                return float(v) if attr in ("d", "f") else int(v)
            except Exception:
                continue
    try:
        return float(value)
    except Exception:
        return str(value)
