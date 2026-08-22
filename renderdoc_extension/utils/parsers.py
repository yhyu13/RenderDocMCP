"""
Parse utility functions for RenderDoc data types.
"""

import renderdoc as rd

from .resource_id import numeric_id
from .rid_cache import resolve_live, remember, lookup_cached


class Parsers:
    """Parse utility functions (static methods)"""

    @staticmethod
    def parse_stage(stage_str):
        """Convert stage string to ShaderStage enum"""
        stage_map = {
            "vertex": rd.ShaderStage.Vertex,
            "hull": rd.ShaderStage.Hull,
            "domain": rd.ShaderStage.Domain,
            "geometry": rd.ShaderStage.Geometry,
            "pixel": rd.ShaderStage.Pixel,
            "compute": rd.ShaderStage.Compute,
        }
        stage_lower = stage_str.lower()
        if stage_lower not in stage_map:
            raise ValueError("Unknown shader stage: %s" % stage_str)
        return stage_map[stage_lower]

    @staticmethod
    def parse_resource_id(resource_id_str, controller=None, ctx=None):
        """Return a *live* ResourceId. Never forge one via ResourceId().id.

        C++ ResourceId.id is private; assigning it from Python leaves Null
        (ResourceId::0). Resolve against cache + GetTextures/GetBuffers/GetResources.
        """
        rid = resolve_live(controller, ctx, resource_id_str)
        if rid is None:
            raise ValueError(
                "Resource not found: %s (cannot construct ResourceId; id is private)"
                % resource_id_str
            )
        return rid

    @staticmethod
    def extract_numeric_id(resource_id_str):
        """Extract numeric ID from resource ID string"""
        return numeric_id(resource_id_str)

    @staticmethod
    def remember_resource_id(rid):
        return remember(rid)

    @staticmethod
    def lookup_cached_resource_id(resource_id_str):
        return lookup_cached(resource_id_str)
