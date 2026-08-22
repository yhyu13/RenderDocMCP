"""
Resource information service for RenderDoc.
"""

import base64

import renderdoc as rd

from ..utils import Parsers
from ..utils.resource_id import ids_equal
from ..utils.rid_cache import remember, resolve_live
from ..utils.tex_stats import (
    channels_from_pixel,
    histogram_channels,
    histogram_range,
    nan_inf_flags,
    reduce_histogram,
    unique_flags,
)


class ResourceService:
    """Resource information service"""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def _find_texture_by_id(self, controller, resource_id):
        """Find texture by resource ID (numeric match against live objects)."""
        for tex in controller.GetTextures() or []:
            remember(tex.resourceId)
            if ids_equal(tex.resourceId, resource_id):
                return tex
        return None

    def _find_buffer_by_id(self, controller, resource_id):
        for buf in controller.GetBuffers() or []:
            remember(buf.resourceId)
            if ids_equal(buf.resourceId, resource_id):
                return buf
        return None

    def _resolve_rid(self, resource_id, controller=None):
        rid = resolve_live(controller, self.ctx, resource_id)
        if rid is None:
            raise ValueError("Resource not found: %s" % resource_id)
        return rid

    def get_buffer_contents(self, resource_id, offset=0, length=0):
        """Get buffer data"""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            buf_desc = self._find_buffer_by_id(controller, resource_id)
            if not buf_desc:
                result["error"] = "Buffer not found: %s" % resource_id
                return
            rid = buf_desc.resourceId

            # Get data
            actual_length = length if length > 0 else buf_desc.length
            data = controller.GetBufferData(rid, offset, actual_length)

            result["data"] = {
                "resource_id": resource_id,
                "length": len(data),
                "total_size": buf_desc.length,
                "offset": offset,
                "content_base64": base64.b64encode(data).decode("ascii"),
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def list_resources(self, resource_type=None, name=None, limit=200):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        if limit is None or int(limit) <= 0:
            limit = 200
        limit = min(int(limit), 2000)
        type_filter = (resource_type or "").lower()
        name_filter = (name or "").lower()
        items = []
        for res in self.ctx.GetResources() or []:
            remember(res.resourceId)
            rid = str(res.resourceId)
            rtype = str(getattr(res, "type", "") or "")
            rname = ""
            try:
                rname = self.ctx.GetResourceName(res.resourceId) or ""
            except Exception:
                rname = getattr(res, "name", "") or ""
            if type_filter and type_filter not in rtype.lower():
                continue
            if name_filter and name_filter not in rname.lower() and name_filter not in rid.lower():
                continue
            items.append({
                "resource_id": rid,
                "type": rtype,
                "name": rname,
            })
        truncated = len(items) > limit
        return {
            "count": len(items),
            "returned": min(len(items), limit),
            "truncated": truncated,
            "resources": items[:limit],
        }

    def get_resource(self, resource_id):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        rid = resolve_live(None, self.ctx, resource_id)
        if rid is None:
            result = {"rid": None}

            def callback(controller):
                result["rid"] = resolve_live(controller, self.ctx, resource_id)

            self._invoke(callback)
            rid = result["rid"]
        if rid is None:
            raise ValueError("Resource not found: %s" % resource_id)
        desc = None
        try:
            desc = self.ctx.GetResource(rid)
        except Exception:
            desc = None
        if desc is None:
            raise ValueError("Resource not found: %s" % resource_id)
        name = ""
        try:
            name = self.ctx.GetResourceName(rid) or ""
        except Exception:
            name = ""
        replaced = False
        replacement = None
        try:
            replaced = bool(self.ctx.IsResourceReplaced(rid))
            if replaced:
                replacement = str(self.ctx.GetResourceReplacement(rid))
        except Exception:
            pass
        info = {
            "resource_id": str(rid),
            "name": name,
            "type": str(getattr(desc, "type", "") or ""),
            "replaced": replaced,
            "replacement_resource_id": replacement,
        }
        try:
            tex = self.ctx.GetTexture(rid)
            if tex:
                info["texture"] = {
                    "width": tex.width,
                    "height": tex.height,
                    "depth": tex.depth,
                    "mips": tex.mips,
                    "format": str(tex.format.Name()),
                }
        except Exception:
            pass
        try:
            buf = self.ctx.GetBuffer(rid)
            if buf:
                info["buffer"] = {"length": buf.length}
        except Exception:
            pass
        return info

    def replace_resource(self, original_resource_id, replacement_resource_id):
        """Swap one capture resource for another already in the capture.

        ReplayController.ReplaceResource applies the swap for subsequent
        replay; CaptureContext.RegisterReplacement makes it UI-visible and
        persistable via save_capture. There is no SetTextureData/SetBufferData
        — you can only swap to another ResourceId (or a compiled shader).
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        result = {"error": None, "original": None, "replacement": None}

        def callback(controller):
            try:
                original = self._resolve_rid(original_resource_id, controller)
                replacement = self._resolve_rid(replacement_resource_id, controller)
            except Exception as e:
                result["error"] = str(e)
                return
            result["original"] = original
            result["replacement"] = replacement
            try:
                controller.ReplaceResource(original, replacement)
            except Exception as e:
                result["error"] = "ReplaceResource failed: %s" % str(e)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        original = result["original"]
        replacement = result["replacement"]
        ui_registered = False
        try:
            self.ctx.RegisterReplacement(original, replacement)
            ui_registered = True
        except Exception:
            ui_registered = False
        return {
            "original_resource_id": str(original),
            "replacement_resource_id": str(replacement),
            "replay_replaced": True,
            "ui_registered": ui_registered,
            "note": (
                "replay + UI replacement; save_capture persists it. "
                "Cannot inject texture/buffer bytes — swap ResourceIds only."
            ),
        }

    def restore_resource(self, original_resource_id):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        result = {"error": None, "original": None}

        def callback(controller):
            try:
                original = self._resolve_rid(original_resource_id, controller)
            except Exception as e:
                result["error"] = str(e)
                return
            result["original"] = original
            try:
                controller.RemoveReplacement(original)
            except Exception as e:
                result["error"] = "RemoveReplacement failed: %s" % str(e)

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        original = result["original"]
        try:
            self.ctx.UnregisterReplacement(original)
        except Exception:
            pass
        return {"resource_id": str(original), "restored": True}

    def restore_all_replacements(self):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        originals = []
        for res in self.ctx.GetResources() or []:
            rid = res.resourceId
            try:
                if self.ctx.IsResourceReplaced(rid):
                    originals.append(rid)
            except Exception:
                continue
        restored = []
        errors = []
        for rid in originals:
            try:
                self.restore_resource(str(rid))
                restored.append(str(rid))
            except Exception as e:
                errors.append({"resource_id": str(rid), "error": str(e)})
        return {"restored": restored, "count": len(restored), "errors": errors}

    def get_texture_stats(self, resource_id, event_id=None, mip=0, slice_idx=0, histogram=False):
        """Per-channel min/max via ReplayController.GetMinMax (GPU, format-aware).

        Never calls GetTextureData. Optional histogram uses GetHistogram over the
        observed float range, then downsamples to 16 buckets. HDR/NaN shows up as
        anomalies, not 'min: 0, max: 255' byte noise.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        result = {"data": None, "error": None}

        def callback(controller):
            if event_id is not None:
                controller.SetFrameEvent(int(event_id), True)
            tex = self._find_texture_by_id(controller, resource_id)
            if tex is None:
                result["error"] = "Texture not found: %s" % resource_id
                return
            sub = rd.Subresource()
            sub.mip = int(mip)
            sub.slice = int(slice_idx)
            try:
                pair = controller.GetMinMax(tex.resourceId, sub, rd.CompType.Typeless)
            except Exception as e:
                result["error"] = "GetMinMax failed: %s" % str(e)
                return
            if not pair or len(pair) < 2:
                result["error"] = "GetMinMax returned no data"
                return
            min_ch = channels_from_pixel(pair[0])
            max_ch = channels_from_pixel(pair[1])
            anomalies = unique_flags(
                nan_inf_flags(min_ch.get("float")),
                nan_inf_flags(max_ch.get("float")),
            )
            fmt = ""
            try:
                fmt = str(tex.format.Name())
            except Exception:
                fmt = ""
            out = {
                "resource_id": resource_id,
                "format": fmt,
                "mip": int(mip),
                "slice": int(slice_idx),
                "min": min_ch,
                "max": max_ch,
                "anomalies": anomalies,
                "note": "GPU GetMinMax; not a CPU byte scan. Prefer pick_pixel for one pixel.",
            }
            if histogram:
                rng = histogram_range(min_ch.get("float"), max_ch.get("float"))
                if rng is None:
                    out["histogram_16"] = []
                    out["histogram_note"] = "skipped: NaN/Inf or degenerate float range"
                else:
                    try:
                        buckets = controller.GetHistogram(
                            tex.resourceId,
                            sub,
                            rd.CompType.Typeless,
                            rng[0],
                            rng[1],
                            histogram_channels(True),
                        )
                    except Exception as e:
                        result["error"] = "GetHistogram failed: %s" % str(e)
                        return
                    out["histogram_16"] = reduce_histogram(buckets)
                    out["histogram_range"] = [rng[0], rng[1]]
            result["data"] = out

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def get_texture_info(self, resource_id):
        """Get texture metadata"""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"texture": None, "error": None}

        def callback(controller):
            try:
                tex_desc = self._find_texture_by_id(controller, resource_id)

                if not tex_desc:
                    result["error"] = "Texture not found: %s" % resource_id
                    return

                result["texture"] = {
                    "resource_id": resource_id,
                    "width": tex_desc.width,
                    "height": tex_desc.height,
                    "depth": tex_desc.depth,
                    "array_size": tex_desc.arraysize,
                    "mip_levels": tex_desc.mips,
                    "format": str(tex_desc.format.Name()),
                    "dimension": str(tex_desc.type),
                    "msaa_samples": tex_desc.msSamp,
                    "byte_size": tex_desc.byteSize,
                }
            except Exception as e:
                import traceback
                result["error"] = "Error: %s\n%s" % (str(e), traceback.format_exc())

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["texture"]

    def get_texture_data(self, resource_id, mip=0, slice=0, sample=0, depth_slice=None):
        """Get texture pixel data."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            tex_desc = self._find_texture_by_id(controller, resource_id)

            if not tex_desc:
                result["error"] = "Texture not found: %s" % resource_id
                return

            # Validate mip level
            if mip < 0 or mip >= tex_desc.mips:
                result["error"] = "Invalid mip level %d (texture has %d mips)" % (
                    mip,
                    tex_desc.mips,
                )
                return

            # Validate slice for array/cube textures
            max_slices = tex_desc.arraysize
            if tex_desc.cubemap:
                max_slices = tex_desc.arraysize * 6
            if slice < 0 or (max_slices > 1 and slice >= max_slices):
                result["error"] = "Invalid slice %d (texture has %d slices)" % (
                    slice,
                    max_slices,
                )
                return

            # Validate sample for MSAA
            if sample < 0 or (tex_desc.msSamp > 1 and sample >= tex_desc.msSamp):
                result["error"] = "Invalid sample %d (texture has %d samples)" % (
                    sample,
                    tex_desc.msSamp,
                )
                return

            # Calculate dimensions at this mip level
            mip_width = max(1, tex_desc.width >> mip)
            mip_height = max(1, tex_desc.height >> mip)
            mip_depth = max(1, tex_desc.depth >> mip)

            # Validate depth_slice for 3D textures
            is_3d = tex_desc.depth > 1
            if depth_slice is not None:
                if not is_3d:
                    result["error"] = "depth_slice can only be used with 3D textures"
                    return
                if depth_slice < 0 or depth_slice >= mip_depth:
                    result["error"] = "Invalid depth_slice %d (texture has %d depth at mip %d)" % (
                        depth_slice,
                        mip_depth,
                        mip,
                    )
                    return

            # Create subresource specification
            sub = rd.Subresource()
            sub.mip = mip
            sub.slice = slice
            sub.sample = sample

            # Get texture data
            try:
                data = controller.GetTextureData(tex_desc.resourceId, sub)
            except Exception as e:
                result["error"] = "Failed to get texture data: %s" % str(e)
                return

            # Extract depth slice for 3D textures if requested
            output_depth = mip_depth
            if is_3d and depth_slice is not None:
                total_size = len(data)
                bytes_per_slice = total_size // mip_depth
                slice_start = depth_slice * bytes_per_slice
                slice_end = slice_start + bytes_per_slice
                data = data[slice_start:slice_end]
                output_depth = 1

            result["data"] = {
                "resource_id": resource_id,
                "width": mip_width,
                "height": mip_height,
                "depth": output_depth,
                "mip": mip,
                "slice": slice,
                "sample": sample,
                "depth_slice": depth_slice,
                "format": str(tex_desc.format.Name()),
                "dimension": str(tex_desc.type),
                "is_3d": is_3d,
                "total_depth": mip_depth if is_3d else 1,
                "data_length": len(data),
                "content_base64": base64.b64encode(data).decode("ascii"),
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def get_resource_usage(self, resource_id):
        """Events that read or write this resource (Texture Viewer / timeline usage strip)."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            rid = resolve_live(controller, self.ctx, resource_id)
            if rid is None:
                result["error"] = "Resource not found: %s" % resource_id
                return
            try:
                usages = controller.GetUsage(rid)
            except Exception as e:
                result["error"] = "GetUsage failed: %s" % str(e)
                return
            events = []
            for u in usages or []:
                events.append({
                    "event_id": getattr(u, "eventId", None),
                    "usage": str(getattr(u, "usage", "")),
                })
            name = ""
            try:
                name = self.ctx.GetResourceName(rid) or ""
            except Exception:
                name = ""
            result["data"] = {
                "resource_id": resource_id,
                "resource_name": name,
                "count": len(events),
                "events": events,
            }

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]
