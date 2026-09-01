"""Shader-step debug (pixel / vertex / compute). Python 3.6 / stdlib only.

Always FreeTrace. Capped queries return a JSON summary, never a full ISA dump;
debug_trace_export walks the full trace to a JSONL file instead.
"""

import renderdoc as rd

from ..utils.debug_trace import (
    anomalies_for,
    cap_states,
    clamp_export_limit,
    clamp_last_n,
    clamp_max_steps,
    collect_states,
    final_variables,
    write_trace_file,
)
from ..utils.export_opts import resolve_export_path

# Shared meta description per stage kind, used in the exported file header.
_EXPORT_HEADER = {
    "pixel": ("pixel", ("event_id", "x", "y")),
    "vertex": ("vertex", ("event_id", "vertex_id", "instance")),
    "compute": ("compute", ("event_id", "group", "thread")),
}


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
        """Capped walk -> summary (names-only states, no full values)."""
        if trace is None or getattr(trace, "debugger", None) is None:
            return {
                "available": False,
                "reason": "shader debugging unavailable (no debug info or API/GPU)",
            }
        max_steps = clamp_max_steps(max_steps)
        last_n = clamp_last_n(last_n)
        try:
            states, _truncated = collect_states(controller, trace.debugger, max_steps)
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

    def _export_trace(self, controller, trace, meta, out_path, limit):
        """Full walk -> JSONL file; return path + stats, never the states."""
        if trace is None or getattr(trace, "debugger", None) is None:
            return {
                "available": False,
                "reason": "shader debugging unavailable (no debug info or API/GPU)",
            }
        states = []
        truncated = False
        try:
            try:
                states, truncated = collect_states(controller, trace.debugger, limit)
            except Exception as e:
                return {"error": "trace walk failed: %s" % str(e)}
            stage = ""
            try:
                stage = str(trace.stage)
            except Exception:
                pass
            finals = final_variables(states[-1] if states else None)
            try:
                write_trace_file(out_path, states, meta)
            except Exception as e:
                return {"error": "trace write failed: %s" % str(e)}
            data = {
                "available": True,
                "path": out_path,
                "total_steps": len(states),
                "truncated": truncated,
                "stage": stage,
                "final_variables": finals,
                "anomalies": anomalies_for(states, finals),
                "kind": meta.get("kind"),
                "note": "full trajectory written to file; slice it with Read/grep, never load it whole",
            }
            return data
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
            data = self._export_trace(
                controller,
                trace,
                {
                    "kind": "pixel",
                    "event_id": int(event_id),
                    "x": int(x),
                    "y": int(y),
                },
                out_path,
                limit,
            )
            if data.get("error"):
                result["error"] = data["error"]
                return
            data["event_id"] = int(event_id)
            data["x"] = int(x)
            data["y"] = int(y)
            result["data"] = data

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def debug_trace_export_vertex(
        self,
        event_id,
        vertex_id,
        instance=0,
        index=None,
        view=0,
        path=None,
        max_steps=None,
    ):
        """Walk the FULL vertex (VS) debug trace to a JSONL file (same contract)."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        limit = clamp_export_limit(max_steps)
        out_path = resolve_export_path(
            path, "trace", "v%d_%d" % (int(event_id), int(vertex_id)), "jsonl"
        )
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
            data = self._export_trace(
                controller,
                trace,
                {
                    "kind": "vertex",
                    "event_id": int(event_id),
                    "vertex_id": int(vertex_id),
                    "instance": int(instance or 0),
                },
                out_path,
                limit,
            )
            if data.get("error"):
                result["error"] = data["error"]
                return
            data["event_id"] = int(event_id)
            data["vertex_id"] = int(vertex_id)
            data["instance"] = int(instance or 0)
            result["data"] = data

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def debug_trace_export_compute(
        self,
        event_id,
        group_x,
        group_y,
        group_z,
        thread_x,
        thread_y,
        thread_z,
        path=None,
        max_steps=None,
    ):
        """Walk the FULL compute (thread) debug trace to a JSONL file."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        limit = clamp_export_limit(max_steps)
        out_path = resolve_export_path(
            path,
            "trace",
            "c%d_%d_%d_%d" % (int(event_id), int(group_x), int(thread_x), int(thread_y)),
            "jsonl",
        )
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
            data = self._export_trace(
                controller,
                trace,
                {
                    "kind": "compute",
                    "event_id": int(event_id),
                    "group": list(group),
                    "thread": list(thread),
                },
                out_path,
                limit,
            )
            if data.get("error"):
                result["error"] = data["error"]
                return
            data["event_id"] = int(event_id)
            data["group"] = list(group)
            data["thread"] = list(thread)
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
