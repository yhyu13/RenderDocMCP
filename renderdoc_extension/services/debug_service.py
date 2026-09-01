"""Shader-step debug (pixel / vertex / compute). Python 3.6 / stdlib only.

Always FreeTrace. Capped queries return a JSON summary, never a full ISA dump;
debug_trace_export walks the full trace to a JSONL file instead.
"""

import renderdoc as rd

from ..utils import Parsers
from ..utils.debug_trace import (
    anomalies_for,
    cap_states,
    clamp_export_limit,
    clamp_last_n,
    clamp_max_steps,
    final_variables,
    write_trace_file,
)
from ..utils.export_opts import resolve_export_path


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

    def debug_trace_export(
        self,
        event_id,
        x,
        y,
        sample=None,
        primitive=None,
        path=None,
        max_steps=None,
    ):
        """Walk the FULL pixel-debug trace, write every state to a JSONL file.

        Response carries the path + stats only, never the states (token rule).
        max_steps=None walks to the natural end; a value stops early.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        limit = clamp_export_limit(max_steps)
        out_path = resolve_export_path(
            path, "trace", "e%d_%d_%d" % (int(event_id), int(x), int(y)), "jsonl"
        )
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
            if trace is None or getattr(trace, "debugger", None) is None:
                result["error"] = "shader debugging unavailable (no debug info or API/GPU)"
                return
            states = []
            truncated = False
            try:
                try:
                    while len(states) < limit:
                        batch = controller.ContinueDebug(trace.debugger)
                        if not batch:
                            break
                        states.extend(batch)
                    if len(states) > limit:
                        states = states[:limit]
                    truncated = len(states) >= limit
                except Exception as e:
                    result["error"] = "trace walk failed: %s" % str(e)
                    return
                stage = ""
                try:
                    stage = str(trace.stage)
                except Exception:
                    pass
                finals = final_variables(states[-1] if states else None)
                try:
                    write_trace_file(
                        out_path,
                        states,
                        {
                            "kind": "pixel",
                            "event_id": int(event_id),
                            "x": int(x),
                            "y": int(y),
                            "stage": stage,
                            "truncated": truncated,
                        },
                    )
                except Exception as e:
                    result["error"] = "trace write failed: %s" % str(e)
                    return
                data = {
                    "available": True,
                    "path": out_path,
                    "total_steps": len(states),
                    "truncated": truncated,
                    "stage": stage,
                    "final_variables": finals,
                    "anomalies": anomalies_for(states, finals),
                    "event_id": int(event_id),
                    "x": int(x),
                    "y": int(y),
                    "note": "full trajectory written to file; slice it with Read/grep, never load it whole",
                }
            finally:
                try:
                    controller.FreeTrace(trace)
                except Exception:
                    pass
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
