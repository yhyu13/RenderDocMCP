"""
Shader edit + replay service for RenderDoc.

Implements the .rdc-internal shader edit/replay loop (perception-agent design
doc §2 / §4): compile HLSL/GLSL -> replace the bound shader -> replay the
event -> read back the render target, all without leaving the capture.

RenderDoc Python API used (verified against v1.45):
    - BuildTargetShader(entry, sourceEncoding, source, compileFlags, stage)
      -> (ResourceId, messages)
    - ReplaceResource(original, replacement)
    - RemoveReplacement(original)
    - SetFrameEvent(eventId, force=True)  # the replay trigger
"""

import base64

import renderdoc as rd

from ..utils import Parsers
from ..utils.compile_opts import bump_glsl_binding_version, resolve_compile_flags
from ..utils.rid_cache import remember, resolve_live


class ShaderEditService:
    """Shader editing and replay operations."""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    @staticmethod
    def _parse_encoding(encoding):
        """Map an encoding name to the ShaderEncoding enum."""
        encoding_map = {
            "hlsl": rd.ShaderEncoding.HLSL,
            "glsl": rd.ShaderEncoding.GLSL,
            "spirv": rd.ShaderEncoding.SPIRV,
            "dxbc": rd.ShaderEncoding.DXBC,
            "dxil": rd.ShaderEncoding.DXIL,
        }
        key = (encoding or "hlsl").lower()
        if key not in encoding_map:
            raise ValueError("Unknown shader encoding: %s" % encoding)
        return encoding_map[key]

    @staticmethod
    def _compile_flags(compile_flags=None):
        """Build a ShaderCompileFlags object from a preset name or pair list.

        ShaderCompileFlags is a struct of name/value pairs; an empty instance
        means "use default compile flags". The 'debug' preset sets
        D3DCOMPILE_DEBUG + D3DCOMPILE_SKIP_OPTIMIZATION (ignored on other APIs).
        """
        pairs = resolve_compile_flags(compile_flags)
        try:
            flags = rd.ShaderCompileFlags()
        except Exception:
            return 0
        for pair in pairs:
            try:
                item = rd.ShaderCompileFlag()
                item.name = pair["name"]
                item.value = pair["value"]
                flags.flags.append(item)
            except Exception:
                continue
        return flags

    def get_shader_source(self, event_id, stage):
        """Get the original source (or raw bytes) of the shader at event/stage."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"source": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)
            pipe = controller.GetPipelineState()
            stage_enum = Parsers.parse_stage(stage)

            shader = pipe.GetShader(stage_enum)
            if shader == rd.ResourceId.Null():
                result["error"] = "No %s shader bound" % stage
                return

            source = {
                "resource_id": str(shader),
                "entry_point": pipe.GetShaderEntryPoint(stage_enum),
                "stage": stage,
            }

            reflection = pipe.GetShaderReflection(stage_enum)
            if reflection is not None:
                enc_name = ""
                try:
                    enc_name = str(reflection.encoding)
                    source["encoding"] = enc_name
                except Exception:
                    pass
                enc_upper = enc_name.upper()
                # rawBytes is the shader in its stored encoding; only high-level
                # source encodings are directly editable.
                source["is_source_text"] = (
                    "HLSL" in enc_upper or "GLSL" in enc_upper or "SPIRVASM" in enc_upper
                )
                try:
                    raw = reflection.rawBytes
                    if raw:
                        source["content_base64"] = base64.b64encode(raw).decode("ascii")
                        source["content_length"] = len(raw)
                except Exception:
                    pass

            result["source"] = source

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["source"]

    def compile_shader(self, hlsl, stage, entry, encoding="hlsl", compile_flags=None):
        """Compile source into a replacement shader for the capture's API."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"compiled": None, "error": None}

        def callback(controller):
            stage_enum = Parsers.parse_stage(stage)
            enc = self._parse_encoding(encoding)
            source_bytes = hlsl.encode("utf-8")
            flags = self._compile_flags(compile_flags)

            shader_id, messages = controller.BuildTargetShader(
                entry, enc, source_bytes, flags, stage_enum
            )
            if shader_id == rd.ResourceId.Null():
                result["error"] = "Shader compile failed: %s" % (messages or "no messages")
                return

            remember(shader_id)
            result["compiled"] = {
                "resource_id": str(shader_id),
                "entry_point": entry,
                "stage": stage,
                "messages": messages or "",
                "compile_flags": resolve_compile_flags(compile_flags),
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["compiled"]

    def replace_shader(self, event_id, stage, compiled_resource_id):
        """Replace the shader bound at event/stage with a compiled shader."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"replacement": None, "error": None}

        def callback(controller):
            # force=False: only move to the event to read the bound shader;
            # the actual replay is driven by replay_event() so the loop does
            # not replay twice per round.
            controller.SetFrameEvent(event_id, False)
            pipe = controller.GetPipelineState()
            stage_enum = Parsers.parse_stage(stage)

            original = pipe.GetShader(stage_enum)
            if original == rd.ResourceId.Null():
                result["error"] = "No %s shader bound" % stage
                return
            remember(original)

            replacement = resolve_live(controller, self.ctx, compiled_resource_id)
            if replacement is None:
                result["error"] = (
                    "compiled shader ResourceId not found: %s "
                    "(compile_shader result must be used in this session)"
                    % compiled_resource_id
                )
                return
            controller.ReplaceResource(original, replacement)
            result["original"] = original
            result["replacement_rid"] = replacement
            result["replacement"] = {
                "original_resource_id": str(original),
                "replacement_resource_id": str(replacement),
                "event_id": event_id,
                "stage": stage,
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        # RegisterReplacement is a UI-thread CaptureContext call. Doing it
        # inside BlockInvoke deadlocks the next replay (replay thread waits
        # for UI, UI waits for replay). Match replace_resource: register after.
        ui_registered = False
        try:
            self.ctx.RegisterReplacement(
                result.get("original"), result.get("replacement_rid")
            )
            ui_registered = True
        except Exception:
            ui_registered = False
        out = result["replacement"]
        out["ui_registered"] = ui_registered
        return out

    def remove_shader_replacement(self, event_id, stage):
        """Remove any shader replacement at event/stage, restoring the original."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"removed": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)
            pipe = controller.GetPipelineState()
            stage_enum = Parsers.parse_stage(stage)

            original = pipe.GetShader(stage_enum)
            if original == rd.ResourceId.Null():
                result["error"] = "No %s shader bound" % stage
                return

            controller.RemoveReplacement(original)
            result["original"] = original
            result["removed"] = {
                "resource_id": str(original),
                "event_id": event_id,
                "stage": stage,
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        try:
            self.ctx.UnregisterReplacement(result.get("original"))
        except Exception:
            pass
        return result["removed"]

    def replay_event(self, event_id):
        """Replay the capture up to event_id, applying any replacements."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"replayed": False}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)
            result["replayed"] = True

        self._invoke(callback)
        result["event_id"] = event_id
        return result

    def get_debug_messages(self):
        """Retrieve newly generated diagnostic/validation messages (L1)."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"messages": []}

        def callback(controller):
            for m in controller.GetDebugMessages():
                item = {"severity": str(m.severity), "message": m.message}
                try:
                    item["category"] = str(m.category)
                except Exception:
                    pass
                try:
                    item["source"] = str(m.source)
                except Exception:
                    pass
                try:
                    item["event_id"] = m.eventId
                except Exception:
                    pass
                result["messages"].append(item)

        self._invoke(callback)
        result["count"] = len(result["messages"])
        return result

    def list_shader_encodings(self):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        out = {"target": [], "custom": []}
        try:
            from ..utils.resource_id import shader_encoding_name
            for enc in self.ctx.CustomShaderEncodings() or []:
                out["custom"].append(shader_encoding_name(enc))
        except Exception:
            pass

        def callback(controller):
            try:
                encs = controller.GetTargetShaderEncodings()
            except Exception:
                encs = None
            if encs is None:
                try:
                    encs = controller.GetCustomShaderEncodings()
                except Exception:
                    encs = []
            from ..utils.resource_id import shader_encoding_name
            for enc in encs or []:
                out["target"].append(shader_encoding_name(enc))

        self._invoke(callback)
        return out

    def list_shaders(self, stage=None, limit=200):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        if limit is None or int(limit) <= 0:
            limit = 200
        limit = min(int(limit), 2000)
        stage_filter = (stage or "").lower()
        seen = {}
        result = {"error": None}

        def callback(controller):
            try:
                from ..utils.helpers import Helpers
                roots = controller.GetRootActions()
                actions = Helpers.flatten_actions(roots)
                stages = Helpers.get_all_shader_stages()
            except Exception as e:
                result["error"] = str(e)
                return
            for action in actions:
                flags = getattr(action, "flags", 0)
                draw_flags = rd.ActionFlags.Drawcall | rd.ActionFlags.Dispatch
                try:
                    draw_flags = draw_flags | rd.ActionFlags.MeshDispatch
                except Exception:
                    pass
                if not (flags & draw_flags):
                    continue
                try:
                    controller.SetFrameEvent(action.eventId, False)
                    pipe = controller.GetPipelineState()
                except Exception:
                    continue
                for st in stages:
                    st_name = str(st).split(".")[-1].lower()
                    if stage_filter and stage_filter not in st_name:
                        continue
                    try:
                        sid = pipe.GetShader(st)
                    except Exception:
                        continue
                    if sid == rd.ResourceId.Null():
                        continue
                    key = str(sid)
                    if key in seen:
                        seen[key]["event_ids"].append(action.eventId)
                        continue
                    entry = ""
                    try:
                        entry = pipe.GetShaderEntryPoint(st) or ""
                    except Exception:
                        entry = ""
                    seen[key] = {
                        "resource_id": key,
                        "stage": st_name,
                        "entry_point": entry,
                        "event_ids": [action.eventId],
                    }

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        items = list(seen.values())
        return {
            "count": len(items),
            "returned": min(len(items), limit),
            "truncated": len(items) > limit,
            "shaders": items[:limit],
        }

    def shader_map(self, limit=200):
        listing = self.list_shaders(limit=limit)
        rows = []
        for s in listing.get("shaders") or []:
            for eid in s.get("event_ids") or []:
                rows.append({
                    "event_id": eid,
                    "stage": s.get("stage"),
                    "resource_id": s.get("resource_id"),
                    "entry_point": s.get("entry_point"),
                })
        rows.sort(key=lambda r: (r["event_id"], r["stage"] or ""))
        truncated = len(rows) > limit
        return {
            "count": len(rows),
            "returned": min(len(rows), limit),
            "truncated": truncated,
            "map": rows[:limit],
        }

    def search_shaders(self, pattern, stage=None, limit=50):
        if not pattern:
            raise ValueError("pattern is required")
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        if limit is None or int(limit) <= 0:
            limit = 50
        limit = min(int(limit), 200)
        needle = pattern.lower()
        matches = []
        listing = self.list_shaders(stage=stage, limit=500)
        result = {"error": None}

        def callback(controller):
            from ..utils.helpers import Helpers
            stages = Helpers.get_all_shader_stages()
            seen_ids = set()
            for s in listing.get("shaders") or []:
                if len(matches) >= limit:
                    return
                sid = s.get("resource_id")
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                eids = s.get("event_ids") or []
                if not eids:
                    continue
                try:
                    controller.SetFrameEvent(int(eids[0]), False)
                    pipe = controller.GetPipelineState()
                    reflection = None
                    stage_enum = None
                    for st in stages:
                        if pipe.GetShader(st) != rd.ResourceId.Null() and str(pipe.GetShader(st)) == sid:
                            stage_enum = st
                            reflection = pipe.GetShaderReflection(st)
                            break
                    if reflection is None:
                        continue
                    targets = controller.GetDisassemblyTargets(True) or []
                    if not targets:
                        continue
                    pipe_obj = pipe.GetGraphicsPipelineObject()
                    disasm = controller.DisassembleShader(pipe_obj, reflection, targets[0]) or ""
                except Exception:
                    continue
                low = disasm.lower()
                idx = low.find(needle)
                if idx < 0:
                    continue
                start = max(0, idx - 80)
                end = min(len(disasm), idx + 80)
                matches.append({
                    "resource_id": sid,
                    "stage": s.get("stage"),
                    "entry_point": s.get("entry_point"),
                    "event_id": eids[0],
                    "snippet": disasm[start:end],
                })

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return {"pattern": pattern, "count": len(matches), "matches": matches}

    def compile_custom_shader(self, source, stage, entry, encoding="hlsl"):
        """BuildCustomShader — visualization shader, not a target replacement."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        result = {"compiled": None, "error": None}
        source = bump_glsl_binding_version(source, encoding)

        def callback(controller):
            stage_enum = Parsers.parse_stage(stage)
            enc = self._parse_encoding(encoding)
            flags = self._compile_flags()
            try:
                shader_id, messages = controller.BuildCustomShader(
                    entry, enc, source.encode("utf-8"), flags, stage_enum
                )
            except Exception as e:
                result["error"] = "BuildCustomShader failed: %s" % str(e)
                return
            if shader_id == rd.ResourceId.Null():
                result["error"] = "Custom shader compile failed: %s" % (messages or "no messages")
                return
            remember(shader_id)
            result["compiled"] = {
                "resource_id": str(shader_id),
                "entry_point": entry,
                "stage": stage,
                "messages": messages or "",
                "custom": True,
            }

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["compiled"]
