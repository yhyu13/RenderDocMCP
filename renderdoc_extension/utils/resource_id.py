"""ResourceId string helpers. Python 3.6, no renderdoc import.

Live OpenGL capture (frame480) showed parse_resource_id constructing
rd.ResourceId() then assigning .id produces ResourceId::0 — the C++ field
is private. Resolution must match against live ResourceId objects (or a
compile-time cache), never by forging a new ResourceId.
"""

NULL_NUMERIC = 0

# renderdoc.ShaderEncoding ordinals (v1.45). OpenGL surfaces these as bare ints
# via SWIG (`str(enc) == "2"`), so name introspection has nothing to walk.
SHADER_ENCODING_BY_VALUE = {
    0: "Unknown",
    1: "DXBC",
    2: "GLSL",
    3: "SPIRV",
    4: "SPIRVAsm",
    5: "OpenGLSPIRV",
    6: "OpenGLSPIRVAsm",
    7: "HLSL",
    8: "DXIL",
    9: "Slang",
}


def numeric_id(resource_id_str):
    """Extract the integer from 'ResourceId::56', '56', or a ResourceId repr."""
    if resource_id_str is None:
        raise ValueError("resource id is required")
    text = str(resource_id_str).strip()
    if not text:
        raise ValueError("resource id is empty")
    if "::" in text:
        text = text.split("::")[-1]
    # SWIG sometimes prints "ResourceId(56)" or trailing junk
    digits = []
    for ch in text:
        if ch.isdigit():
            digits.append(ch)
        elif digits:
            break
    if not digits:
        raise ValueError("Invalid resource ID: %s" % resource_id_str)
    return int("".join(digits))


def is_null_id(resource_id_str):
    try:
        return numeric_id(resource_id_str) == NULL_NUMERIC
    except Exception:
        return True


def ids_equal(a, b):
    """True only if both parse to the same *non-null* numeric id."""
    try:
        na = numeric_id(a)
        nb = numeric_id(b)
    except Exception:
        return False
    if na == NULL_NUMERIC or nb == NULL_NUMERIC:
        return False
    return na == nb


def shader_encoding_name(enc):
    """Prefer 'GLSL' over '2' (SWIG enum int stringification)."""
    if enc is None:
        return ""
    try:
        name = getattr(enc, "name", None)
        if name:
            return str(name)
    except Exception:
        pass
    text = str(enc)
    if "." in text:
        tail = text.split(".")[-1]
        if tail and not tail.isdigit():
            return tail
    enum_type = getattr(enc, "__class__", None)
    if enum_type is not None:
        for attr in dir(enum_type):
            if attr.startswith("_"):
                continue
            try:
                if getattr(enum_type, attr) == enc:
                    return attr
            except Exception:
                continue
    try:
        n = int(enc)
        mapped = SHADER_ENCODING_BY_VALUE.get(n)
        if mapped:
            return mapped
    except Exception:
        pass
    try:
        n = int(text)
        mapped = SHADER_ENCODING_BY_VALUE.get(n)
        if mapped:
            return mapped
    except Exception:
        pass
    return text


def resource_format_name(fmt):
    if fmt is None:
        return ""
    try:
        name = fmt.Name()
        if name:
            return str(name)
    except Exception:
        pass
    text = str(fmt)
    if "Swig" in text or "0x" in text:
        return ""
    return text


def sane_mip_count(value, fallback=None):
    """Drop garbage like num_mips=233 from an uninitialized Descriptor field."""
    try:
        n = int(value)
    except Exception:
        n = None
    if n is not None and 1 <= n <= 32:
        return n
    if fallback is None:
        return None
    try:
        f = int(fallback)
    except Exception:
        return None
    if 1 <= f <= 32:
        return f
    return None
