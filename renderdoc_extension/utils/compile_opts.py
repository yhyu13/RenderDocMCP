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


def bump_glsl_binding_version(source, encoding="glsl"):
    """OpenGL custom shaders: layout(binding=N) needs GLSL 420.

    RenderDoc's custom-shader wrapper injects a binding qualifier. Source
    at #version 330 then fails with C7532. Bump only when encoding is glsl,
    the first line is #version < 420, and the body already uses layout+binding.
    """
    if (encoding or "").lower() != "glsl" or not source:
        return source
    src = source.lstrip()
    if not src.startswith("#version"):
        return source
    if "layout" not in source or "binding" not in source:
        return source
    first = src.splitlines()[0]
    ver = first.replace("#version", "").strip().split()[0]
    try:
        if int(ver) < 420:
            return source.replace(first, "#version 420", 1)
    except Exception:
        return source
    return source
