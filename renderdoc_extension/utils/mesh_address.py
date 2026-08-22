"""Indexed vs non-indexed vertex addressing.

Python 3.6 / stdlib only. No renderdoc import so tests can load this
module without a GPU. MeshService uses these offsets so sampled input
vertices correspond to sampled indices.
"""

import struct


def index_fetch_offset(ib_byte_offset, index_offset, index_stride):
    """Byte offset of the first index for this draw (indexOffset * stride)."""
    return int(ib_byte_offset) + int(index_offset or 0) * int(index_stride)


def vertex_ids_from_indices(indices, base_vertex):
    """Apply baseVertex to fetched indices (indexed draws only)."""
    base = int(base_vertex or 0)
    return [int(i) + base for i in indices]


def vertex_fetch_offset(attr_byte_offset, vb_byte_offset, vertex_index, stride):
    """Byte offset of one vertex attribute in a VB."""
    return (
        int(attr_byte_offset)
        + int(vb_byte_offset)
        + int(vertex_index) * int(stride)
    )


def decode_attr_at_vertex_ids(data, stride, vertex_ids, vmin, nfloats):
    """Unpack float attributes for vertex_ids from a span starting at vmin.

    ``data`` is the bytes of vertices [vmin, vmax] packed at ``stride``.
    Returns a list of {vertex_index, values} (values is None if truncated).
    """
    out = []
    if stride <= 0 or nfloats <= 0:
        return out
    need = int(nfloats) * 4
    buf = data
    for vtx in vertex_ids:
        local = int(vtx) - int(vmin)
        start = local * int(stride)
        if start < 0 or start + need > len(buf):
            out.append({"vertex_index": int(vtx), "values": None})
            continue
        values = list(struct.unpack_from("<" + "f" * int(nfloats), buf, start))
        out.append({"vertex_index": int(vtx), "values": values})
    return out


def vertex_span(vertex_ids, max_span=None):
    """Inclusive (vmin, count) for non-negative ids, or None if sparse/empty.

    Negative ids are ignored for the span (they are holes, not vertex 0).
    """
    ids = [int(v) for v in vertex_ids if int(v) >= 0]
    if not ids:
        return None
    vmin = min(ids)
    vmax = max(ids)
    span = vmax - vmin + 1
    if max_span is None:
        # 16× sample count, floor 256 verts: dense strips stay one fetch;
        # a 0/1e6 pair is sparse and must not pull a giant VB span.
        max_span = max(len(vertex_ids) * 16, 256)
    if span <= 0 or span > max_span:
        return None
    return (vmin, span)


def sample_vertices_at_ids(
    vertex_ids,
    stride,
    nfloats,
    attr_name,
    get_bytes,
    attr_byte_offset,
    vb_byte_offset,
):
    """Fetch first-used attribute at each vertex id via ``get_bytes(off, len)``.

    GPU-free: tests pass a bytes slice; MeshService wraps GetBufferData.
    Negative ids are not fetched. Sparse ranges fetch per-vertex.
    """
    verts = []
    if not vertex_ids or stride <= 0 or nfloats <= 0:
        return verts

    span = vertex_span(vertex_ids)
    decoded = None
    if span is not None:
        vmin, count = span
        byte_off = vertex_fetch_offset(
            attr_byte_offset, vb_byte_offset, vmin, stride
        )
        raw = get_bytes(byte_off, count * stride)
        if raw is None:
            decoded = None
        else:
            decoded = decode_attr_at_vertex_ids(
                raw, stride, vertex_ids, vmin, nfloats
            )

    if decoded is None:
        decoded = []
        for vtx in vertex_ids:
            vtx = int(vtx)
            if vtx < 0:
                decoded.append({"vertex_index": vtx, "values": None})
                continue
            byte_off = vertex_fetch_offset(
                attr_byte_offset, vb_byte_offset, vtx, stride
            )
            raw = get_bytes(byte_off, stride)
            need = int(nfloats) * 4
            if raw is None or len(raw) < need:
                decoded.append({"vertex_index": vtx, "values": None})
            else:
                values = list(struct.unpack_from("<" + "f" * int(nfloats), raw, 0))
                decoded.append({"vertex_index": vtx, "values": values})

    for i, item in enumerate(decoded):
        verts.append(
            {
                "index": i,
                "vertex_index": item["vertex_index"],
                "name": attr_name,
                "values": item["values"],
            }
        )
    return verts
