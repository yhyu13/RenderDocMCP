"""Duck-typed ShaderDebugTrace summary. Python 3.6 / no renderdoc.

Debug* traces are huge; MCP returns a cap, never the full ISA dump.
Full-fidelity trajectory goes to a file instead (serialize_state_full /
write_trace_file) — path + stats ride in the response, states never do.
"""

import io
import json
import os

DEFAULT_MAX_STEPS = 64
HARD_MAX_STEPS = 256
DEFAULT_LAST_N = 8
HARD_LAST_N = 32
# Export walks the full trace; this only bounds a pathological run whose
# ContinueDebug never empties (real PS traces are ~10k-15k steps).
EXPORT_HARD_MAX_STEPS = 1000000


def clamp_export_limit(max_steps):
    """None -> hard ceiling; otherwise a positive int bounded by the ceiling."""
    if max_steps is None:
        return EXPORT_HARD_MAX_STEPS
    n = int(max_steps)
    if n <= 0:
        raise ValueError("max_steps must be a positive integer")
    return min(n, EXPORT_HARD_MAX_STEPS)


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


def collect_states(controller, debugger, limit):
    """Walk ``ContinueDebug`` up to ``limit`` states. GPU-free duck-typed.

    Shared by the capped summary queries and the full export walk so the
    drain loop lives next to the other trace utilities (renderdoc-free), not
    beside the ``import renderdoc`` in debug_service.py. The caller owns
    FreeTrace; this only drains. Returns (states, truncated).
    """
    states = []
    while len(states) < limit:
        batch = controller.ContinueDebug(debugger)
        if not batch:
            break
        states.extend(batch)
    if len(states) > limit:
        states = states[:limit]
    return states, len(states) >= limit


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
        # Match serialize_state_full / summarize_state: some backends (e.g. GL)
        # leave the *after* var name empty; fall back to the *before* variant so
        # the name survives. Without this, final_variables comes back [] on GL.
        name = _var_name(after) or _var_name(getattr(ch, "before", None))
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


def _clean_value(raw):
    """JSON-safe full-width vector; NaN/Inf become string markers."""
    out = []
    for v in raw:
        try:
            f = float(v)
        except Exception:
            out.append(v)
            continue
        if f != f:
            out.append("NaN")
        elif f == float("inf"):
            out.append("Inf")
        elif f == float("-inf"):
            out.append("-Inf")
        else:
            out.append(v)
    return out


def _var_full_value(var):
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
            return _clean_value([raw[i] for i in range(len(raw))])
        except Exception:
            return None
    return None


def serialize_state_full(st):
    """Full-fidelity state: step/flags plus every change's before/after values."""
    changes_out = []
    for ch in list(getattr(st, "changes", None) or []):
        before = getattr(ch, "before", None)
        after = getattr(ch, "after", None)
        name = _var_name(after) or _var_name(before)
        changes_out.append(
            {
                "name": name,
                "before": _var_full_value(before),
                "after": _var_full_value(after),
            }
        )
    return {
        "step": getattr(st, "stepIndex", None),
        "next_instruction": getattr(st, "nextInstruction", None),
        "flags": str(getattr(st, "flags", "") or ""),
        "changes": changes_out,
    }


def write_trace_file(path, states, meta):
    """JSONL dump: line 1 header meta, then one serialized state per line.

    Returns the number of states written. Creates missing parent dirs.
    """
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    header = dict(meta or {})
    header["type"] = "header"
    count = 0
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(header, ensure_ascii=True))
        fh.write("\n")
        for st in states:
            fh.write(json.dumps(serialize_state_full(st), ensure_ascii=True))
            fh.write("\n")
            count += 1
    return count


def anomalies_for(states, finals):
    hits = flag_anomalies(
        " ".join(str(getattr(s, "flags", "") or "") for s in states or [])
    ) + value_anomalies(finals)
    seen = set()
    uniq = []
    for a in hits:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    return uniq


def cap_states(states, last_n):
    items = list(states)
    last_n = clamp_last_n(last_n)
    truncated = len(items) > last_n
    kept = items[-last_n:] if last_n else []
    finals = final_variables(kept[-1] if kept else None)
    return {
        "count": len(items),
        "returned": len(kept),
        "truncated": truncated,
        "states": [summarize_state(s) for s in kept],
        "final_variables": finals,
        "anomalies": anomalies_for(items, finals),
    }
