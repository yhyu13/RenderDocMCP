"""Compile-flag presets for BuildTargetShader. Python 3.6, no renderdoc.

ShaderCompileFlags is a list of {name, value} pairs. 'debug' maps to the D3D
flags that keep symbols and skip optimisation — required for useful
debug_pixel / source-level stepping. Other APIs ignore unknown names.
"""

PRESETS = {
    "default": (),
    "debug": (
        {"name": "D3DCOMPILE_DEBUG", "value": "1"},
        {"name": "D3DCOMPILE_SKIP_OPTIMIZATION", "value": "1"},
    ),
}


def resolve_compile_flags(compile_flags):
    """Return a list of {name, value} dicts.

    Accepts None/'default'/'debug', or an already-resolved list of dicts.
    """
    if compile_flags is None or compile_flags == "":
        return []
    if isinstance(compile_flags, (list, tuple)):
        out = []
        for item in compile_flags:
            if not isinstance(item, dict) or "name" not in item:
                raise ValueError("compile_flags list items must be {name, value} dicts")
            out.append({
                "name": str(item.get("name") or ""),
                "value": str(item.get("value") or ""),
            })
        return out
    key = str(compile_flags).lower().strip()
    if key not in PRESETS:
        raise ValueError(
            "Unknown compile_flags: %s (want %s)" % (compile_flags, ", ".join(PRESETS))
        )
    return [dict(p) for p in PRESETS[key]]
