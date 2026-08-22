"""Capture-file section caps. Python 3.6, no renderdoc.

GetSectionContents has no prefix-read: a framecapture section is hundreds of MB.
Refuse to materialize anything above SECTION_LOAD_CAP.
"""

SECTION_LOAD_CAP = 4 * 1024 * 1024
SECTION_JSON_CAP = 65536
SECTION_WRITE_CAP = 65536

SAFE_SECTION_TYPES = ("unknown", "notes", "bookmarks", "resrenames")

_SECTION_TYPE_ENUM = {
    "unknown": "Unknown",
    "notes": "Notes",
    "bookmarks": "Bookmarks",
    "resrenames": "ResourceRenames",
}


def section_type_enum_name(section_type):
    key = (section_type or "unknown").lower().strip()
    if key not in _SECTION_TYPE_ENUM:
        raise ValueError(
            "section_type must be one of: %s" % ", ".join(SAFE_SECTION_TYPES)
        )
    return _SECTION_TYPE_ENUM[key]


def clamp_section_json_bytes(max_bytes):
    n = int(max_bytes or 4096)
    if n <= 0:
        n = 4096
    if n > SECTION_JSON_CAP:
        n = SECTION_JSON_CAP
    return n


def section_load_allowed(uncompressed_size, cap=SECTION_LOAD_CAP):
    if uncompressed_size is None:
        return True
    try:
        return int(uncompressed_size) <= int(cap)
    except Exception:
        return False


def encode_section_contents(contents):
    if contents is None:
        return b""
    if isinstance(contents, (bytes, bytearray)):
        raw = bytes(contents)
    else:
        raw = str(contents).encode("utf-8")
    if len(raw) > SECTION_WRITE_CAP:
        raise ValueError("contents exceeds %d bytes" % SECTION_WRITE_CAP)
    return raw
