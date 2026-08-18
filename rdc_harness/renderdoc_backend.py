"""RenderDoc-side adapter for the shader-fix loop (doc3 §4.3).

Implements :class:`rdc_harness.orchestrator.ShaderBackend` against the RenderDoc
ReplayController. This module lives on the **AI/MCP side** of the hybrid
process split (standard Python >= 3.10) and must NOT be imported from inside
``renderdoc_extension/``, which runs RenderDoc's embedded Python 3.6 and would
fail to parse these annotations.

The concrete RenderDoc calls are intentionally not implemented yet: they
require the MCP bridge to expose compile / inject / replay / verify tools. Each
method raises ``NotImplementedError`` and documents the exact controller API
plus the extension file it maps to, so the integration seam is explicit and a
future PR only fills in bodies.
"""

from __future__ import annotations

from typing import Any

from .orchestrator import ShaderBackend


class RenderDocShaderBackend(ShaderBackend):
    """ShaderBackend targeting the RenderDoc ReplayController.

    Construct with either a raw ``pyrenderdoc`` ReplayController (obtained via
    ``ctx.Replay().BlockInvoke(...)``) or the MCP bridge client object that
    exposes ``.call(method, params)``. Supply whichever is available; methods
    will use it once implemented.
    """

    def __init__(self, controller: Any = None, bridge: Any = None):
        self._controller = controller
        self._bridge = bridge

    def compile_shader(self, hlsl: str, stage: str) -> bytes:
        # Maps to: renderdoc_extension/services/ + a DXC/glslang compile step,
        # exposed as a new MCP tool (e.g. "compile_shader") and called via
        # self._bridge.call("compile_shader", {...}).
        raise NotImplementedError(
            "compile_shader requires a RenderDoc-side compile tool; "
            "expose DXC/glslang in renderdoc_extension and call via the bridge."
        )

    def inject_shader(self, event_id: int, stage: str, bytecode: bytes) -> None:
        # Maps to: controller.SetShaderBytes(event_id, ShaderStage.<stage>, bytecode)
        # (doc3 §4.3). No MCP tool exists yet.
        raise NotImplementedError(
            "inject_shader maps to controller.SetShaderBytes; "
            "no MCP tool exposes it yet."
        )

    def replay(self, event_id: int) -> None:
        # Maps to: controller.ReplayEvent(event_id, event_id, ReplayFlags.Replay_AllDraws)
        raise NotImplementedError(
            "replay maps to controller.ReplayEvent; no MCP tool exposes it yet."
        )

    def run_l1(self):
        # L1 = fetch get_frame_summary() + get_pipeline_state(event_id), then
        # rdc_harness.rules.run_deterministic(...).
        raise NotImplementedError(
            "run_l1 maps to MCP get_frame_summary + get_pipeline_state, "
            "then rdc_harness.rules.run_deterministic."
        )

    def run_l2(self):
        # L2 = fetch get_texture_data(resource_id), then
        # rdc_harness.behavioral.run_behavioral(actual, golden).
        raise NotImplementedError(
            "run_l2 maps to MCP get_texture_data vs golden, "
            "then rdc_harness.behavioral.run_behavioral."
        )
