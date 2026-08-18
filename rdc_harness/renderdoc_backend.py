"""RenderDoc-side adapter for the shader-fix loop (doc3 §4.3).

Implements :class:`rdc_harness.orchestrator.ShaderBackend` by driving the MCP
bridge to the RenderDoc extension. The extension exposes the compile / replace /
replay / verify primitives (see
``renderdoc_extension/services/shader_edit_service.py``); this backend turns
those primitives into the loop the orchestrator needs.

This module lives on the **AI/MCP side** of the hybrid process split
(standard Python >= 3.10) and must NOT be imported from inside
``renderdoc_extension/``, which runs RenderDoc's embedded Python 3.6 and would
fail to parse these annotations.
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from .behavioral import run_behavioral
from .models import VerificationReport
from .orchestrator import ShaderBackend, ShaderCompileError
from .rules import run_deterministic


class RenderDocShaderBackend(ShaderBackend):
    """ShaderBackend driving the RenderDoc extension via the MCP bridge.

    Construct with an MCP bridge client exposing ``.call(method, params)``.
    A raw ``pyrenderdoc`` ReplayController may also be supplied for API
    compatibility, but direct-controller mode is not implemented; use the
    bridge (the supported MCP runtime path).

    Loop configuration:
        - ``event_id``: the target draw/dispatch.
        - ``entry``: the shader entry point; discovered from the capture via
          ``get_shader_source`` when omitted.
        - ``golden_bytes`` / ``render_target``: the L2 baseline image bytes and
          the render-target resource id to diff against after replay.
    """

    def __init__(
        self,
        controller: Any = None,
        bridge: Any = None,
        event_id: Optional[int] = None,
        entry: Optional[str] = None,
        golden_bytes: Optional[bytes] = None,
        render_target: Optional[str] = None,
    ):
        self._controller = controller
        self._bridge = bridge
        self._event_id = event_id
        self._entry = entry
        self._golden_bytes = golden_bytes
        self._render_target = render_target

    def _call(self, method: str, params: Optional[dict[str, Any]] = None) -> Any:
        if self._bridge is None:
            raise RuntimeError(
                "RenderDocShaderBackend requires an MCP bridge client; "
                "direct controller mode is not implemented."
            )
        return self._bridge.call(method, params)

    def _require_event(self) -> int:
        if self._event_id is None:
            raise ValueError(
                "event_id is required; set it on RenderDocShaderBackend"
            )
        return self._event_id

    def _discover_entry(self, stage: str) -> str:
        if self._entry is None:
            source = self._call(
                "get_shader_source",
                {"event_id": self._require_event(), "stage": stage},
            )
            self._entry = source.get("entry_point")
            if not self._entry:
                raise ShaderCompileError("could not determine shader entry point")
        return self._entry

    def compile_shader(self, hlsl: str, stage: str) -> str:
        entry = self._discover_entry(stage)
        result = self._call(
            "compile_shader", {"hlsl": hlsl, "stage": stage, "entry": entry}
        )
        if not result.get("resource_id"):
            raise ShaderCompileError(result.get("messages") or "compile failed")
        return result["resource_id"]

    def inject_shader(self, event_id: int, stage: str, compiled: str) -> None:
        self._call(
            "replace_shader",
            {"event_id": event_id, "stage": stage, "compiled_resource_id": compiled},
        )

    def replay(self, event_id: int) -> None:
        self._call("replay_event", {"event_id": event_id})

    def run_l1(self) -> VerificationReport:
        summary = self._call("get_frame_summary") or {}
        pipeline = self._call(
            "get_pipeline_state", {"event_id": self._require_event()}
        )
        debug = self._call("get_debug_messages") or {}
        statistics = summary.get("statistics") or {}
        frame = {"api_stats": {"draw_calls": statistics.get("draw_calls")}}
        return run_deterministic(
            frame, pipeline=pipeline, debug_messages=debug.get("messages", [])
        )

    def run_l2(self) -> VerificationReport:
        if self._golden_bytes is None:
            raise ValueError("golden_bytes is required for L2 behavioral verification")
        if self._render_target is None:
            raise ValueError("render_target resource id is required for L2")
        tex = self._call("get_texture_data", {"resource_id": self._render_target})
        actual = base64.b64decode(tex["content_base64"])
        if len(actual) != len(self._golden_bytes):
            raise ValueError(
                "render target size mismatch vs golden: actual=%d golden=%d"
                % (len(actual), len(self._golden_bytes))
            )
        if len(actual) % 4 != 0:
            raise ValueError(
                "render target is not 4-bytes-per-pixel (RGBA8): format=%s"
                % tex.get("format", "unknown")
            )
        fmt = (tex.get("format") or "").upper()
        if any(tok in fmt for tok in ("FLOAT", "UINT", "SINT", "TYPELESS", "16", "32", "10")):
            raise ValueError(
                "L2 behavioral diff only supports 8-bit RGBA render targets; "
                "got format=%s" % tex.get("format")
            )
        return run_behavioral(actual, self._golden_bytes)
