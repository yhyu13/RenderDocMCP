"""Export path / file-type helpers. Python 3.6, no renderdoc import."""

import os
import tempfile

FILE_TYPE_ENUM = {
    "png": "PNG",
    "jpg": "JPG",
    "bmp": "BMP",
    "tga": "TGA",
    "hdr": "HDR",
    "exr": "EXR",
    "raw": "Raw",
    "dds": "DDS",
}
FILE_TYPES = tuple(FILE_TYPE_ENUM.keys())

_JPEG_ALIAS = "jpg"


def normalize_file_type(name):
    key = (name or "png").lower().strip()
    if key == "jpeg":
        key = _JPEG_ALIAS
    if key not in FILE_TYPES:
        raise ValueError("Unknown image type: %s (want %s)" % (name, ", ".join(FILE_TYPES)))
    return key


def default_export_dir():
    path = os.path.join(tempfile.gettempdir(), "renderdoc_mcp", "exports")
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def resolve_export_path(path, prefix, resource_id, file_type):
    """Return an absolute path; generate one under the IPC export dir if omitted."""
    ext = file_type if file_type != "jpeg" else "jpg"
    if path:
        return path
    safe = str(resource_id).replace(":", "_").replace("/", "_").replace("\\", "_")
    return os.path.join(default_export_dir(), "%s_%s.%s" % (prefix, safe, ext))
