"""Shader-step debug (pixel / vertex / compute). Python 3.6 / stdlib only.

Always FreeTrace. Returns a capped JSON summary, never a full ISA dump.
"""

import renderdoc as rd

from ..utils import Parsers
from ..utils.debug_trace import cap_states, clamp_max_steps, clamp_last_n


class DebugService:
    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def _no_pref(self):
        try:
            return rd.ReplayController.NoPreference
        except Exception:
            return 0xFFFFFFFF

    def _run_trace(self, controller, trace, max_steps, last_n):
        if trace is None or getattr(trace, "debugger", None) is None:
            return {
                "available": False,
                "reason": "shader debugging unavailable (no debug info or API/GPU)",
            }
        max_steps = clamp_max_steps(max_steps)
        last_n = clamp_last_n(last_n)
        states = []
        steps = 0
        try:
            while steps < max_steps:
                batch = controller.ContinueDebug(trace.debugger)
                if not batch:
                    break
                for st in batch:
                    states.append(st)
                    steps += 1
                    if steps >= max_steps:
                        break
            summary = cap_states(states, last_n)
            summary["available"] = True
            summary["max_steps"] = max_steps
            try:
                summary["stage"] = str(trace.stage)
            except Exception:
                pass
            return summary
        finally:
            try:
                controller.FreeTrace(trace)
            except Exception:
                pass

    def debug_pixel(
        self,
        event_id,
        x,
        y,
        sample=None,
        primitive=None,
        max_steps=64,
        last_n=8,
    ):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        result = {"data": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(int(event_id), True)
            nopref = self._no_pref()
            try:
                inputs = rd.DebugPixelInputs()
                inputs.sample = int(sample) if sample is not None else nopref
                inputs.primitive = int(primitive) if primitive is not None else nopref
                trace = controller.DebugPixel(int(x), int(y), inputs)
            except Exception as e:
                result["error"] = "DebugPixel failed: %s" % str(e)
                return
            data = self._run_trace(controller, trace, max_steps, last_n)
            data["event_id"] = int(event_id)
            data["x"] = int(x)
            data["y"] = int(y)
            data["note"] = "x/y are top-left even on GL; trace is capped"
            result["data"] = data

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def debug_vertex(
        self, event_id, vertex_id, instance=0, index=None, view=0, max_steps=64, last_n=8
    ):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        result = {"data": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(int(event_id), True)
            idx = int(index) if index is not None else int(vertex_id)
            try:
                trace = controller.DebugVertex(
                    int(vertex_id), int(instance or 0), idx, int(view or 0)
                )
            except Exception as e:
                result["error"] = "DebugVertex failed: %s" % str(e)
                return
            data = self._run_trace(controller, trace, max_steps, last_n)
            data["event_id"] = int(event_id)
            data["vertex_id"] = int(vertex_id)
            data["instance"] = int(instance or 0)
            result["data"] = data

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def debug_thread(
        self,
        event_id,
        group_x,
        group_y,
        group_z,
        thread_x,
        thread_y,
        thread_z,
        max_steps=64,
        last_n=8,
    ):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        result = {"data": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(int(event_id), True)
            group = (int(group_x), int(group_y), int(group_z))
            thread = (int(thread_x), int(thread_y), int(thread_z))
            try:
                trace = controller.DebugThread(group, thread)
            except Exception as e:
                result["error"] = "DebugThread failed: %s" % str(e)
                return
            data = self._run_trace(controller, trace, max_steps, last_n)
            data["event_id"] = int(event_id)
            data["group"] = list(group)
            data["thread"] = list(thread)
            result["data"] = data

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]
