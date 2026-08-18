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
    def _compile_flags():
        """Return default compile flags for BuildTargetShader.

        ShaderCompileFlags is a struct of name/value pairs in the Python
        bindings; an empty instance means "use default compile flags".
        """
        try:
            return rd.ShaderCompileFlags()
        except Exception:
            return 0

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
            flags = compile_flags if compile_flags is not None else self._compile_flags()

            shader_id, messages = controller.BuildTargetShader(
                entry, enc, source_bytes, flags, stage_enum
            )
            if shader_id == rd.ResourceId.Null():
                result["error"] = "Shader compile failed: %s" % (messages or "no messages")
                return

            result["compiled"] = {
                "resource_id": str(shader_id),
                "entry_point": entry,
                "stage": stage,
                "messages": messages or "",
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

            replacement = Parsers.parse_resource_id(compiled_resource_id)
            controller.ReplaceResource(original, replacement)

            result["replacement"] = {
                "original_resource_id": str(original),
                "replacement_resource_id": str(replacement),
                "event_id": event_id,
                "stage": stage,
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["replacement"]

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
            result["removed"] = {
                "resource_id": str(original),
                "event_id": event_id,
                "stage": stage,
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
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
