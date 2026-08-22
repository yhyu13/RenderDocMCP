"""Duck-typed ShaderDebugTrace summary. Python 3.6 / no renderdoc.

Debug* traces are huge; MCP returns a cap, never the full ISA dump.
"""

DEFAULT_MAX_STEPS = 64
HARD_MAX_STEPS = 256
DEFAULT_LAST_N = 8
HARD_LAST_N = 32


def clamp_max_steps(n):
    if n is None or int(n) <= 0:
        return DEFAULT_MAX_STEPS
    n = int(n)
    if n > HARD_MAX_STEPS:
        return HARD_MAX_STEPS
    return n


def clamp_last_n(n):
    if n is None or int(n) <= 0:
        return DEFAULT_LAST_N
    n = int(n)
    if n > HARD_LAST_N:
        return HARD_LAST_N
    return n


def _var_name(var):
    if var is None:
        return ""
    return getattr(var, "name", "") or ""


def _var_value(var):
    if var is None:
        return None
    val = getattr(var, "value", None)
    if val is None:
        return None
    for attr in ("f32v", "u32v", "s32v"):
        raw = getattr(val, attr, None)
        if raw is None:
            continue
        try:
            return [raw[i] for i in range(min(4, len(raw)))]
        except Exception:
            try:
                return [raw[0], raw[1], raw[2], raw[3]]
            except Exception:
                return None
    return None


def summarize_state(st):
    flags = str(getattr(st, "flags", "") or "")
    changes = getattr(st, "changes", None) or []
    names = []
    for ch in list(changes)[:16]:
        after = getattr(ch, "after", None)
        name = _var_name(after) or _var_name(getattr(ch, "before", None))
        if name:
            names.append(name)
    return {
        "step": getattr(st, "stepIndex", None),
        "next_instruction": getattr(st, "nextInstruction", None),
        "flags": flags,
        "changed": names,
    }


def final_variables(st, limit=24):
    """Source-mapped-ish names from the last state's changes."""
    if st is None:
        return []
    out = []
    seen = set()
    for ch in list(getattr(st, "changes", None) or []):
        after = getattr(ch, "after", None)
        name = _var_name(after)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "value": _var_value(after)})
        if len(out) >= int(limit):
            break
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


def flag_anomalies(flags):
    text = str(flags or "").lower()
    hits = []
    for token in ("nan", "inf", "discard"):
        if token in text:
            hits.append(token)
    return hits


def value_anomalies(variables):
    hits = []
    for item in variables or []:
        val = item.get("value") if isinstance(item, dict) else None
        seq = val if isinstance(val, (list, tuple)) else (val,)
        for v in seq:
            if _is_nan_or_inf(v):
                hits.append("nan_or_inf")
                return hits
    return hits


def cap_states(states, last_n):
    items = list(states)
    last_n = clamp_last_n(last_n)
    truncated = len(items) > last_n
    kept = items[-last_n:] if last_n else []
    finals = final_variables(kept[-1] if kept else None)
    flags_text = " ".join(str(getattr(s, "flags", "") or "") for s in items)
    anomalies = flag_anomalies(flags_text) + value_anomalies(finals)
    seen = set()
    uniq = []
    for a in anomalies:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    return {
        "count": len(items),
        "returned": len(kept),
        "truncated": truncated,
        "states": [summarize_state(s) for s in kept],
        "final_variables": finals,
        "anomalies": uniq,
    }
