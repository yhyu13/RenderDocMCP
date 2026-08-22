"""Save textures / RTs / thumbnail to disk. Python 3.6 / stdlib only.

Images never ride in response.json — only the path and metadata.
"""

import os

import renderdoc as rd

from ..utils import Parsers
from ..utils.export_opts import FILE_TYPE_ENUM, normalize_file_type, resolve_export_path
from ..utils.resource_id import ids_equal
from ..utils.rid_cache import remember, resolve_live
from ..utils.mesh_obj import mesh_to_obj


class ExportService:
    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def _file_type(self, dest_type):
        key = normalize_file_type(dest_type)
        name = FILE_TYPE_ENUM[key]
        return getattr(rd.FileType, name), key

    def _resolve_texture_id(self, controller, resource_id):
        rid = resolve_live(controller, self.ctx, resource_id)
        if rid is not None:
            return rid
        for tex in controller.GetTextures() or []:
            remember(tex.resourceId)
            if ids_equal(tex.resourceId, resource_id):
                return tex.resourceId
        return None

    def _texture_save(self, controller, resource_id, dest_enum, mip, slice_idx, sample):
        rid = self._resolve_texture_id(controller, resource_id)
        if rid is None:
            raise ValueError("Texture not found: %s" % resource_id)
        s = rd.TextureSave()
        s.resourceId = rid
        s.destType = dest_enum
        s.mip = int(mip)
        try:
            s.slice.sliceIndex = int(slice_idx)
        except Exception:
            pass
        try:
            s.sample.sampleIndex = int(sample)
        except Exception:
            pass
        try:
            s.alpha = rd.AlphaMapping.Preserve
        except Exception:
            pass
        return s

    def export_texture(
        self,
        resource_id,
        path=None,
        mip=0,
        slice_idx=0,
        sample=0,
        dest_type="png",
    ):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        dest_enum, key = self._file_type(dest_type)
        out_path = resolve_export_path(path, "tex", resource_id, key)
        parent = os.path.dirname(out_path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)

        result = {"data": None, "error": None}

        def callback(controller):
            try:
                saver = self._texture_save(
                    controller, resource_id, dest_enum, mip, slice_idx, sample
                )
            except Exception as e:
                result["error"] = str(e)
                return
            try:
                details = controller.SaveTexture(saver, out_path)
            except Exception as e:
                result["error"] = "SaveTexture failed: %s" % str(e)
                return
            ok = True
            msg = ""
            try:
                ok = bool(details.OK())
                msg = details.Message() if not ok else ""
            except Exception:
                ok = os.path.isfile(out_path)
            if not ok:
                result["error"] = "SaveTexture failed: %s" % (msg or "unknown")
                return
            width = height = None
            try:
                tex = self.ctx.GetTexture(saver.resourceId)
                if tex:
                    width = int(tex.width)
                    height = int(tex.height)
            except Exception:
                pass
            result["data"] = {
                "path": out_path,
                "resource_id": str(resource_id),
                "format": key,
                "mip": int(mip),
                "slice": int(slice_idx),
                "sample": int(sample),
                "width": width,
                "height": height,
            }

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def export_render_target(
        self, event_id, path=None, target_index=0, dest_type="png"
    ):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        action = self.ctx.GetAction(int(event_id))
        rid = None
        if action is not None:
            outs = list(getattr(action, "outputs", []) or [])
            idx = int(target_index or 0)
            if 0 <= idx < len(outs) and outs[idx] != rd.ResourceId.Null():
                rid = remember(outs[idx])
        if rid is None:
            raise ValueError("No color target %s at event %s" % (target_index, event_id))
        return self.export_texture(
            str(rid), path=path, dest_type=dest_type
        )

    def get_thumbnail(self, path=None, dest_type="png"):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        last = None
        try:
            last = self.ctx.GetLastAction()
        except Exception:
            last = None
        rid = None
        event_id = None
        walk = last
        while walk is not None and rid is None:
            event_id = getattr(walk, "eventId", None)
            for output in getattr(walk, "outputs", []) or []:
                if output != rd.ResourceId.Null():
                    rid = remember(output)
                    break
            walk = getattr(walk, "previous", None)
        if rid is None:
            try:
                pipe = self.ctx.CurPipelineState()
                for desc in pipe.GetOutputTargets() or []:
                    output = getattr(desc, "resource", None) or getattr(desc, "resourceId", None)
                    if output is not None and output != rd.ResourceId.Null():
                        rid = remember(output)
                        break
            except Exception:
                rid = None
        if rid is None:
            raise ValueError("No color output found for thumbnail")
        data = self.export_texture(str(rid), path=path, dest_type=dest_type)
        data["event_id"] = event_id
        data["note"] = "last present/draw color target, not the embedded capture thumbnail"
        return data

    def export_buffer(self, resource_id, path=None, offset=0, length=0):
        """Write buffer bytes to disk. Response is the path, never the bytes."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        out_path = resolve_export_path(path, "buf", resource_id, "bin")
        parent = os.path.dirname(out_path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        result = {"data": None, "error": None}

        def callback(controller):
            buf_desc = None
            for buf in controller.GetBuffers() or []:
                remember(buf.resourceId)
                if ids_equal(buf.resourceId, resource_id):
                    buf_desc = buf
                    break
            if buf_desc is not None:
                rid = buf_desc.resourceId
            else:
                rid = None
            if buf_desc is None:
                result["error"] = "Buffer not found: %s" % resource_id
                return
            actual = int(length) if int(length or 0) > 0 else buf_desc.length
            try:
                data = controller.GetBufferData(rid, int(offset or 0), actual)
            except Exception as e:
                result["error"] = "GetBufferData failed: %s" % str(e)
                return
            try:
                with open(out_path, "wb") as fh:
                    fh.write(bytes(data) if data is not None else b"")
            except Exception as e:
                result["error"] = "write failed: %s" % str(e)
                return
            result["data"] = {
                "path": out_path,
                "resource_id": str(resource_id),
                "offset": int(offset or 0),
                "length": 0 if data is None else len(data),
                "total_size": buf_desc.length,
            }

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]
