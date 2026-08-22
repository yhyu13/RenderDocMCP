"""Pixel pick + pixel history — the human Texture Viewer loop.

Python 3.6 / stdlib only. ReplayController access via BlockInvoke.
"""

import renderdoc as rd


class PixelService:
    """Pick a pixel and retrieve its modification history."""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def _resolve_texture(self, controller, resource_id, event_id):
        """Resolve a texture ResourceId; fall back to the action's first color output."""
        if resource_id:
            from ..utils.rid_cache import resolve_live, remember
            rid = resolve_live(controller, self.ctx, resource_id)
            if rid is None:
                raise ValueError("Texture not found: %s" % resource_id)
            return remember(rid)

        action = self.ctx.GetAction(event_id)
        if action is not None:
            for output in action.outputs:
                if output != rd.ResourceId.Null():
                    return output

        pipe = controller.GetPipelineState()
        try:
            targets = pipe.GetOutputTargets()
            for desc in targets:
                rid = getattr(desc, "resource", None) or getattr(desc, "resourceId", None)
                if rid is not None and rid != rd.ResourceId.Null():
                    return rid
        except Exception:
            pass
        return None

    def _subresource(self, mip, slice_idx, sample):
        sub = rd.Subresource()
        sub.mip = mip
        sub.slice = slice_idx
        sub.sample = sample
        return sub

    @staticmethod
    def _pixel_value(val):
        if val is None:
            return None
        out = {}
        try:
            out["float"] = [float(c) for c in val.floatValue[:4]]
        except Exception:
            out["float"] = None
        try:
            out["uint"] = [int(c) for c in val.uintValue[:4]]
        except Exception:
            out["uint"] = None
        try:
            out["int"] = [int(c) for c in val.intValue[:4]]
        except Exception:
            out["int"] = None
        return out

    @staticmethod
    def _mod_value(mv):
        if mv is None:
            return {"valid": False}
        valid = True
        try:
            valid = bool(mv.IsValid())
        except Exception:
            pass
        col = None
        try:
            col = [float(c) for c in mv.col.floatValue[:4]]
        except Exception:
            col = None
        return {
            "valid": valid,
            "color": col,
            "depth": getattr(mv, "depth", None),
            "stencil": getattr(mv, "stencil", None),
        }

    @staticmethod
    def _serialize_mod(mod):
        passed = False
        try:
            passed = bool(mod.Passed())
        except Exception:
            passed = False
        return {
            "event_id": getattr(mod, "eventId", None),
            "passed": passed,
            "frag_index": getattr(mod, "fragIndex", 0),
            "primitive_id": getattr(mod, "primitiveID", 0),
            "pre": PixelService._mod_value(getattr(mod, "preMod", None)),
            "shader_out": PixelService._mod_value(getattr(mod, "shaderOut", None)),
            "post": PixelService._mod_value(getattr(mod, "postMod", None)),
            "failed": {
                "depth": bool(getattr(mod, "depthTestFailed", False)),
                "stencil": bool(getattr(mod, "stencilTestFailed", False)),
                "backface": bool(getattr(mod, "backfaceCulled", False)),
                "scissor": bool(getattr(mod, "scissorClipped", False)),
                "shader_discard": bool(getattr(mod, "shaderDiscarded", False)),
                "depth_clip": bool(getattr(mod, "depthClipped", False)),
                "viewport": bool(getattr(mod, "viewClipped", False)),
                "sample_mask": bool(getattr(mod, "sampleMasked", False)),
                "unbound_ps": bool(getattr(mod, "unboundPS", False)),
                "predication": bool(getattr(mod, "predicationSkipped", False)),
                "direct_shader_write": bool(getattr(mod, "directShaderWrite", False)),
            },
        }

    def pick_pixel(
        self,
        event_id,
        x,
        y,
        resource_id=None,
        mip=0,
        slice_idx=0,
        sample=0,
    ):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(int(event_id), True)
            rid = self._resolve_texture(controller, resource_id, int(event_id))
            if rid is None:
                result["error"] = "No color target bound; pass resource_id"
                return
            sub = self._subresource(mip, slice_idx, sample)
            try:
                val = controller.PickPixel(rid, int(x), int(y), sub, rd.CompType.Typeless)
            except Exception as e:
                result["error"] = "PickPixel failed: %s" % str(e)
                return
            result["data"] = {
                "event_id": int(event_id),
                "resource_id": str(rid),
                "x": int(x),
                "y": int(y),
                "mip": mip,
                "slice": slice_idx,
                "sample": sample,
                "note": "x/y are top-left even on GL",
                "value": self._pixel_value(val),
            }

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def get_pixel_history(
        self,
        event_id,
        x,
        y,
        resource_id=None,
        mip=0,
        slice_idx=0,
        sample=0,
        max_events=32,
    ):
        """Who wrote this pixel — the killer human feature.

        Caps the returned list (default 32). Pixel history can be slow or
        unsupported; failures come back as an error string, not a crash.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        if max_events is None or int(max_events) <= 0:
            max_events = 32
        if int(max_events) > 128:
            max_events = 128

        result = {"data": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(int(event_id), True)
            rid = self._resolve_texture(controller, resource_id, int(event_id))
            if rid is None:
                result["error"] = "No color target bound; pass resource_id"
                return
            sub = self._subresource(mip, slice_idx, sample)
            try:
                history = controller.PixelHistory(
                    rid, int(x), int(y), sub, rd.CompType.Typeless
                )
            except Exception as e:
                result["error"] = "PixelHistory failed (unsupported or GPU error): %s" % str(e)
                return
            if history is None:
                result["error"] = "PixelHistory returned no data (unsupported on this GPU/API)"
                return
            serialized = [self._serialize_mod(mod) for mod in history]
            passing = 0
            for item in serialized:
                if item.get("passed"):
                    passing += 1
            truncated = len(serialized) > int(max_events)
            kept = serialized[: int(max_events)]
            result["data"] = {
                "event_id": int(event_id),
                "resource_id": str(rid),
                "x": int(x),
                "y": int(y),
                "count": len(serialized),
                "returned": len(kept),
                "truncated": truncated,
                "passing": passing,
                "events": kept,
            }

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]
