"""GPU counters, event snapshot, capture sections. Python 3.6 / stdlib only."""

import base64

import renderdoc as rd

from ..utils.capture_access import pick_capture_access
from ..utils.counters import counter_value
from ..utils.sections import (
    SECTION_LOAD_CAP,
    clamp_section_json_bytes,
    encode_section_contents,
    section_load_allowed,
    section_type_enum_name,
)


class AnalysisService:
    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def get_counters(self, event_id=None, name_filter=None, list_only=False):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        result = {"data": None, "error": None}
        needle = (name_filter or "").lower()

        def callback(controller):
            try:
                available = list(controller.EnumerateCounters() or [])
            except Exception as e:
                result["error"] = "EnumerateCounters failed: %s" % str(e)
                return
            descs = []
            wanted = []
            for c in available:
                desc = None
                try:
                    desc = controller.DescribeCounter(c)
                except Exception:
                    desc = None
                name = str(getattr(desc, "name", None) or c)
                unit = str(getattr(desc, "unit", "") or "")
                item = {"id": str(c), "name": name, "unit": unit}
                if needle and needle not in name.lower() and needle not in item["id"].lower():
                    continue
                descs.append(item)
                wanted.append(c)
            if list_only:
                result["data"] = {"available": True, "counters": descs, "count": len(descs)}
                return
            try:
                results = controller.FetchCounters(wanted) if wanted else []
            except Exception as e:
                result["error"] = "FetchCounters failed: %s" % str(e)
                return
            samples = []
            for r in results or []:
                eid = getattr(r, "eventId", None)
                if event_id is not None and int(eid or -1) != int(event_id):
                    continue
                samples.append({
                    "event_id": eid,
                    "counter": str(getattr(r, "counter", "")),
                    "value": counter_value(getattr(r, "value", None)),
                })
                if len(samples) >= 200:
                    break
            result["data"] = {
                "available": True,
                "counters": descs,
                "samples": samples,
                "sample_count": len(samples),
                "truncated": len(samples) >= 200,
            }

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def get_snapshot(self, event_id):
        """Compact event snapshot: action + RT ids + shader ids. Not a full dump."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        action = self.ctx.GetAction(int(event_id))
        if action is None:
            raise ValueError("No action at event %d" % event_id)
        flags = str(getattr(action, "flags", ""))
        name = ""
        try:
            name = action.GetName(self.ctx.GetStructuredFile())
        except Exception:
            name = getattr(action, "customName", "") or ""
        outputs = []
        for o in getattr(action, "outputs", []) or []:
            if o != rd.ResourceId.Null():
                outputs.append(str(o))
        depth = getattr(action, "depthOut", None)
        snapshot = {
            "event_id": int(event_id),
            "name": name,
            "flags": flags,
            "num_indices": getattr(action, "numIndices", 0),
            "num_instances": getattr(action, "numInstances", 0),
            "outputs": outputs,
            "depth_target": str(depth) if depth and depth != rd.ResourceId.Null() else None,
        }
        result = {"shaders": {}}

        def callback(controller):
            controller.SetFrameEvent(int(event_id), True)
            pipe = controller.GetPipelineState()
            from ..utils.helpers import Helpers
            for st in Helpers.get_all_shader_stages():
                sid = pipe.GetShader(st)
                if sid == rd.ResourceId.Null():
                    continue
                result["shaders"][str(st).split(".")[-1].lower()] = {
                    "resource_id": str(sid),
                    "entry_point": pipe.GetShaderEntryPoint(st),
                }

        self._invoke(callback)
        snapshot["shaders"] = result["shaders"]
        return snapshot

    def list_sections(self):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        cap, reason = pick_capture_access(self.ctx)
        if cap is None:
            return {"count": 0, "sections": [], "note": reason}
        n = 0
        try:
            n = int(cap.GetSectionCount())
        except Exception:
            n = 0
        sections = []
        for i in range(n):
            try:
                props = cap.GetSectionProperties(i)
            except Exception:
                continue
            sections.append({
                "index": i,
                "name": getattr(props, "name", ""),
                "type": str(getattr(props, "type", "")),
                "uncompressed_size": getattr(props, "uncompressedSize", None),
            })
        return {"count": len(sections), "sections": sections}

    def get_section(self, index=None, name=None, max_bytes=4096):
        """Read one capture-file section as capped base64.

        GetSectionContents has no prefix-read. If uncompressedSize is above
        SECTION_LOAD_CAP (4 MiB) we refuse rather than materializing a
        multi-hundred-MB framecapture into Python 3.6.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        cap, reason = pick_capture_access(self.ctx)
        if cap is None:
            raise ValueError(reason)
        if index is None:
            if not name:
                raise ValueError("index or name is required")
            try:
                index = cap.FindSectionByName(name)
            except Exception:
                index = -1
            if index is None or int(index) < 0:
                raise ValueError("section not found: %s" % name)
        index = int(index)
        try:
            props = cap.GetSectionProperties(index)
        except Exception as e:
            raise ValueError("section properties failed: %s" % str(e))
        uncompressed = getattr(props, "uncompressedSize", None)
        if not section_load_allowed(uncompressed):
            raise ValueError(
                "section too large to load (%s bytes; cap %d). Use list_sections."
                % (uncompressed, SECTION_LOAD_CAP)
            )
        try:
            raw = cap.GetSectionContents(index) or b""
        except Exception as e:
            raise ValueError("section read failed: %s" % str(e))
        max_bytes = clamp_section_json_bytes(max_bytes)
        truncated = len(raw) > max_bytes
        chunk = raw[:max_bytes]
        return {
            "index": index,
            "name": getattr(props, "name", ""),
            "type": str(getattr(props, "type", "")),
            "size": len(raw),
            "truncated": truncated,
            "content_base64": base64.b64encode(chunk).decode("ascii"),
        }

    def write_section(self, name, contents, section_type="unknown"):
        """Write/overwrite a small capture-file section (WriteSection).

        Restricted to notes/bookmarks/resrenames/unknown. FrameCapture and
        other internal sections are rejected. Contents cap SECTION_WRITE_CAP.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        if not name:
            raise ValueError("name is required")
        enum_name = section_type_enum_name(section_type)
        raw = encode_section_contents(contents)
        cap, reason = pick_capture_access(self.ctx)
        if cap is None:
            raise ValueError(reason)
        try:
            props = rd.SectionProperties()
            props.name = str(name)
            props.type = getattr(rd.SectionType, enum_name)
            props.uncompressedSize = len(raw)
        except Exception as e:
            raise ValueError("SectionProperties failed: %s" % str(e))
        try:
            details = cap.WriteSection(props, raw)
        except Exception as e:
            raise ValueError("WriteSection failed: %s" % str(e))
        ok = True
        msg = ""
        try:
            ok = bool(details.OK())
            msg = details.Message() if not ok else ""
        except Exception:
            ok = True
        if not ok:
            raise ValueError("WriteSection failed: %s" % (msg or "unknown"))
        return {
            "name": str(name),
            "type": enum_name,
            "bytes": len(raw),
            "note": "written into the open capture file; save_capture to persist a copy",
        }
