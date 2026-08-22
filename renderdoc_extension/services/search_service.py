"""
Reverse lookup search service for RenderDoc.
"""

import renderdoc as rd

from ..utils import Parsers, Helpers
from ..utils.resource_id import ids_equal
from ..utils.rid_cache import remember


class SearchService:
    """Reverse lookup search service"""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def _search_draws(self, matcher_fn):
        """
        Common template for searching draw calls.

        Args:
            matcher_fn: Function(pipe, controller, action, ctx) -> match_reason or None
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"matches": [], "scanned_draws": 0}

        def callback(controller):
            root_actions = controller.GetRootActions()
            structured_file = controller.GetStructuredFile()
            all_actions = Helpers.flatten_actions(root_actions)

            # Filter to only draw calls and dispatches
            draw_actions = [
                a for a in all_actions
                if a.flags & (rd.ActionFlags.Drawcall | rd.ActionFlags.Dispatch)
            ]
            result["scanned_draws"] = len(draw_actions)

            for action in draw_actions:
                controller.SetFrameEvent(action.eventId, False)
                pipe = controller.GetPipelineState()

                match_reason = matcher_fn(pipe, controller, action, self.ctx)
                if match_reason:
                    result["matches"].append({
                        "event_id": action.eventId,
                        "name": action.GetName(structured_file),
                        "match_reason": match_reason,
                    })

        self._invoke(callback)
        result["total_matches"] = len(result["matches"])
        return result

    def find_draws_by_shader(self, shader_name, stage=None):
        """Find all draw calls using a shader with the given name (partial match)."""
        # Determine which stages to check
        if stage:
            stages_to_check = [Parsers.parse_stage(stage)]
        else:
            stages_to_check = Helpers.get_all_shader_stages()

        def matcher(pipe, controller, action, ctx):
            for s in stages_to_check:
                shader = pipe.GetShader(s)
                if shader == rd.ResourceId.Null():
                    continue

                reflection = pipe.GetShaderReflection(s)
                if reflection:
                    entry_point = pipe.GetShaderEntryPoint(s)
                    shader_debug_name = ""
                    try:
                        shader_debug_name = ctx.GetResourceName(shader)
                    except Exception:
                        pass

                    if shader_name.lower() in entry_point.lower():
                        return "%s entry_point: '%s'" % (str(s), entry_point)
                    elif shader_debug_name and shader_name.lower() in shader_debug_name.lower():
                        return "%s name: '%s'" % (str(s), shader_debug_name)
            return None

        return self._search_draws(matcher)

    def find_draws_by_texture(self, texture_name):
        """Find all draw calls using a texture with the given name (partial match)."""
        stages_to_check = Helpers.get_all_shader_stages()

        def matcher(pipe, controller, action, ctx):
            # Check SRVs (read-only resources)
            for stage in stages_to_check:
                try:
                    srvs = pipe.GetReadOnlyResources(stage, False)
                    for srv in srvs:
                        if srv.descriptor.resource == rd.ResourceId.Null():
                            continue
                        res_name = ""
                        try:
                            res_name = ctx.GetResourceName(srv.descriptor.resource)
                        except Exception:
                            pass
                        if res_name and texture_name.lower() in res_name.lower():
                            return "%s SRV: '%s'" % (str(stage), res_name)
                except Exception:
                    pass

                # Check UAVs (read-write resources)
                try:
                    uavs = pipe.GetReadWriteResources(stage, False)
                    for uav in uavs:
                        if uav.descriptor.resource == rd.ResourceId.Null():
                            continue
                        res_name = ""
                        try:
                            res_name = ctx.GetResourceName(uav.descriptor.resource)
                        except Exception:
                            pass
                        if res_name and texture_name.lower() in res_name.lower():
                            return "%s UAV: '%s'" % (str(stage), res_name)
                except Exception:
                    pass

            # Check render targets
            try:
                om = pipe.GetOutputMerger()
                if om:
                    for i, rt in enumerate(om.renderTargets):
                        if rt.resourceId != rd.ResourceId.Null():
                            res_name = ""
                            try:
                                res_name = ctx.GetResourceName(rt.resourceId)
                            except Exception:
                                pass
                            if res_name and texture_name.lower() in res_name.lower():
                                return "RenderTarget[%d]: '%s'" % (i, res_name)
            except Exception:
                pass

            return None

        return self._search_draws(matcher)

    def find_draws_by_resource(self, resource_id):
        """Find all draw calls using a specific resource ID (exact match)."""
        stages_to_check = Helpers.get_all_shader_stages()

        def matcher(pipe, controller, action, ctx):
            # Check shaders — never compare against a forged Null ResourceId.
            for stage in stages_to_check:
                shader = pipe.GetShader(stage)
                remember(shader)
                if ids_equal(shader, resource_id):
                    return "%s shader" % str(stage)

            # Check SRVs and UAVs
            for stage in stages_to_check:
                try:
                    srvs = pipe.GetReadOnlyResources(stage, False)
                    for srv in srvs:
                        live = srv.descriptor.resource
                        remember(live)
                        if ids_equal(live, resource_id):
                            return "%s SRV slot %d" % (str(stage), srv.access.index)
                except Exception:
                    pass

                try:
                    uavs = pipe.GetReadWriteResources(stage, False)
                    for uav in uavs:
                        live = uav.descriptor.resource
                        remember(live)
                        if ids_equal(live, resource_id):
                            return "%s UAV slot %d" % (str(stage), uav.access.index)
                except Exception:
                    pass

            # Check render targets
            try:
                om = pipe.GetOutputMerger()
                if om:
                    for i, rt in enumerate(om.renderTargets):
                        remember(rt.resourceId)
                        if ids_equal(rt.resourceId, resource_id):
                            return "RenderTarget[%d]" % i
                    remember(om.depthTarget.resourceId)
                    if ids_equal(om.depthTarget.resourceId, resource_id):
                        return "DepthTarget"
            except Exception:
                pass

            return None

        return self._search_draws(matcher)
