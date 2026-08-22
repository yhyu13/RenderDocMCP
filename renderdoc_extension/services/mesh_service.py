"""Mesh input vs VS output — Matias's first tool for 'the mesh looks wrong'.

Python 3.6 / stdlib only. Samples a handful of vertices (default 8) so the
payload stays token-small. VSIn is assembled from IA bindings; VSOut comes
from GetPostVSData (VSIn is not a valid GetPostVSData stage).
"""

import struct

import renderdoc as rd

from ..utils.mesh_address import (
    index_fetch_offset,
    sample_vertices_at_ids,
    vertex_fetch_offset,
    vertex_ids_from_indices,
)


class MeshService:
    """Sample mesh input / vertex-shader output at an event."""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    @staticmethod
    def _unpack_indices(data, stride, count):
        if not data or stride not in (2, 4) or count <= 0:
            return []
        fmt = "<I" if stride == 4 else "<H"
        out = []
        for i in range(count):
            start = i * stride
            if start + stride > len(data):
                break
            out.append(struct.unpack_from(fmt, data, start)[0])
        return out

    @staticmethod
    def _unpack_floats(data, offset, nfloats):
        need = nfloats * 4
        if offset + need > len(data):
            return None
        return list(struct.unpack_from("<" + "f" * nfloats, data, offset))

    def _sample_vertices_at_ids(
        self, controller, vb, first_attr, vtx_ids, stride, nfloats, attr_name
    ):
        """Fetch the first used attribute at each (index + baseVertex) id."""

        def get_bytes(offset, length):
            return controller.GetBufferData(vb.resourceId, offset, length)

        return sample_vertices_at_ids(
            vtx_ids,
            stride,
            nfloats,
            attr_name,
            get_bytes,
            first_attr.byteOffset,
            vb.byteOffset,
        )

    def get_mesh_data(self, event_id, max_vertices=8):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        if max_vertices is None or int(max_vertices) <= 0:
            max_vertices = 8
        if int(max_vertices) > 64:
            max_vertices = 64
        max_vertices = int(max_vertices)

        result = {"data": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(int(event_id), True)
            action = self.ctx.GetAction(int(event_id))
            if action is None:
                result["error"] = "No action at event %d" % event_id
                return

            pipe = controller.GetPipelineState()
            indexed = bool(action.flags & rd.ActionFlags.Indexed)
            topology = None
            try:
                topology = str(pipe.GetPrimitiveTopology())
            except Exception:
                topology = None

            payload = {
                "event_id": int(event_id),
                "num_indices": action.numIndices,
                "num_instances": action.numInstances,
                "indexed": indexed,
                "topology": topology,
                "input": {"attributes": [], "sample_vertices": [], "sample_indices": []},
                "output": {
                    "available": False,
                    "stride": 0,
                    "sample_vertices": [],
                },
            }

            # ---- VSIn from IA ------------------------------------------------
            try:
                ib = pipe.GetIBuffer()
                vbs = pipe.GetVBuffers()
                attrs = pipe.GetVertexInputs()
            except Exception as e:
                payload["input"]["error"] = str(e)
                attrs = []
                vbs = []
                ib = None

            first_attr = None
            for attr in attrs or []:
                info = {
                    "name": getattr(attr, "name", ""),
                    "used": bool(getattr(attr, "used", True)),
                    "per_instance": bool(getattr(attr, "perInstance", False)),
                    "vertex_buffer": getattr(attr, "vertexBuffer", 0),
                    "byte_offset": getattr(attr, "byteOffset", 0),
                }
                try:
                    from ..utils.resource_id import resource_format_name
                    info["format"] = resource_format_name(attr.format)
                except Exception:
                    info["format"] = ""
                payload["input"]["attributes"].append(info)
                if first_attr is None and info["used"] and not info["per_instance"]:
                    first_attr = attr

            n = min(max_vertices, action.numIndices if action.numIndices > 0 else max_vertices)

            if indexed and ib is not None and ib.resourceId != rd.ResourceId.Null():
                try:
                    ib_off = index_fetch_offset(
                        ib.byteOffset, action.indexOffset, max(ib.byteStride, 1)
                    )
                    raw = controller.GetBufferData(
                        ib.resourceId, ib_off, n * max(ib.byteStride, 1)
                    )
                    payload["input"]["sample_indices"] = self._unpack_indices(
                        raw, ib.byteStride, n
                    )
                except Exception as e:
                    payload["input"]["index_error"] = str(e)

            if first_attr is not None and vbs:
                vb_index = first_attr.vertexBuffer
                if 0 <= vb_index < len(vbs):
                    vb = vbs[vb_index]
                    stride = vb.byteStride or 0
                    try:
                        comp_count = int(first_attr.format.compCount)
                    except Exception:
                        comp_count = 4
                    if stride <= 0:
                        stride = max(comp_count, 1) * 4
                    attr_name = getattr(first_attr, "name", "")
                    nfloats = min(comp_count, 4)
                    try:
                        if indexed:
                            vtx_ids = vertex_ids_from_indices(
                                payload["input"]["sample_indices"],
                                action.baseVertex,
                            )
                            verts = self._sample_vertices_at_ids(
                                controller,
                                vb,
                                first_attr,
                                vtx_ids,
                                stride,
                                nfloats,
                                attr_name,
                            )
                        else:
                            byte_off = vertex_fetch_offset(
                                first_attr.byteOffset,
                                vb.byteOffset,
                                action.vertexOffset,
                                stride,
                            )
                            raw = controller.GetBufferData(
                                vb.resourceId, byte_off, n * stride
                            )
                            verts = []
                            for i in range(n):
                                vals = self._unpack_floats(
                                    raw, i * stride, nfloats
                                )
                                if vals is None:
                                    break
                                verts.append(
                                    {
                                        "index": i,
                                        "vertex_index": action.vertexOffset + i,
                                        "name": attr_name,
                                        "values": vals,
                                    }
                                )
                        payload["input"]["sample_vertices"] = verts
                    except Exception as e:
                        payload["input"]["vertex_error"] = str(e)

            # ---- VSOut from analysis -----------------------------------------
            try:
                postvs = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
            except Exception as e:
                payload["output"]["error"] = str(e)
                postvs = None

            if postvs is not None and postvs.vertexResourceId != rd.ResourceId.Null():
                stride = postvs.vertexByteStride or 0
                out_count = postvs.numIndices or action.numIndices
                n_out = min(max_vertices, out_count if out_count > 0 else max_vertices)
                payload["output"]["available"] = True
                payload["output"]["stride"] = stride
                payload["output"]["resource_id"] = str(postvs.vertexResourceId)
                payload["output"]["num_indices"] = out_count
                if stride >= 16 and n_out > 0:
                    try:
                        raw = controller.GetBufferData(
                            postvs.vertexResourceId,
                            postvs.vertexByteOffset,
                            n_out * stride,
                        )
                        verts = []
                        for i in range(n_out):
                            pos = self._unpack_floats(raw, i * stride, 4)
                            if pos is None:
                                break
                            item = {"index": i, "position": pos}
                            w = pos[3]
                            if w != 0.0:
                                item["ndc_xy"] = [pos[0] / w, pos[1] / w]
                            verts.append(item)
                        payload["output"]["sample_vertices"] = verts
                    except Exception as e:
                        payload["output"]["error"] = str(e)

            result["data"] = payload

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]
