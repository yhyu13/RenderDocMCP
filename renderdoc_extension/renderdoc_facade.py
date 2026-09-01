"""
RenderDoc API Facade
Provides thread-safe access to RenderDoc's ReplayController and CaptureContext.
Uses BlockInvoke to marshal calls to the replay thread.
"""

from .services import (
    CaptureManager,
    ActionService,
    SearchService,
    ResourceService,
    PipelineService,
    ShaderEditService,
    PixelService,
    MeshService,
    ExportService,
    DebugService,
    AnalysisService,
)


class RenderDocFacade:
    """
    Facade for RenderDoc API access.

    This class delegates all operations to specialized service classes:
    - CaptureManager: Capture management (status, list, open)
    - ActionService: Draw call / action operations
    - SearchService: Reverse lookup searches
    - ResourceService: Texture and buffer data
    - PipelineService: Pipeline state and shader info
    """

    def __init__(self, ctx):
        """
        Initialize facade with CaptureContext.

        Args:
            ctx: The pyrenderdoc CaptureContext from register()
        """
        self.ctx = ctx

        # Initialize service classes
        self._capture = CaptureManager(ctx, self._invoke)
        self._action = ActionService(ctx, self._invoke)
        self._search = SearchService(ctx, self._invoke)
        self._resource = ResourceService(ctx, self._invoke)
        self._pipeline = PipelineService(ctx, self._invoke)
        self._shader_edit = ShaderEditService(ctx, self._invoke)
        self._pixel = PixelService(ctx, self._invoke)
        self._mesh = MeshService(ctx, self._invoke)
        self._export = ExportService(ctx, self._invoke)
        self._debug = DebugService(ctx, self._invoke)
        self._analysis = AnalysisService(ctx, self._invoke)

    def _invoke(self, callback):
        """Invoke callback on replay thread via BlockInvoke"""
        self.ctx.Replay().BlockInvoke(callback)

    # ==================== Capture Management ====================

    def get_capture_status(self):
        """Check if a capture is loaded and get API info"""
        return self._capture.get_capture_status()

    def list_captures(self, directory):
        """List all .rdc files in the specified directory"""
        return self._capture.list_captures(directory)

    def open_capture(self, capture_path):
        """Open a capture file in RenderDoc"""
        return self._capture.open_capture(capture_path)

    # ==================== Draw Call / Action Operations ====================

    def get_draw_calls(
        self,
        include_children=True,
        marker_filter=None,
        exclude_markers=None,
        event_id_min=None,
        event_id_max=None,
        only_actions=False,
        flags_filter=None,
        preset=None,
    ):
        """Get all draw calls/actions in the capture with optional filtering"""
        return self._action.get_draw_calls(
            include_children=include_children,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
            event_id_min=event_id_min,
            event_id_max=event_id_max,
            only_actions=only_actions,
            flags_filter=flags_filter,
            preset=preset,
        )

    def get_frame_summary(self):
        """Get a summary of the current capture frame"""
        return self._action.get_frame_summary()

    def get_draw_call_details(self, event_id):
        """Get detailed information about a specific draw call"""
        return self._action.get_draw_call_details(event_id)

    def get_action_timings(self, event_ids=None, marker_filter=None, exclude_markers=None):
        """Get GPU timing information for actions"""
        return self._action.get_action_timings(
            event_ids=event_ids,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
        )

    # ==================== Search Operations ====================

    def find_draws_by_shader(self, shader_name, stage=None):
        """Find all draw calls using a shader with the given name (partial match)"""
        return self._search.find_draws_by_shader(shader_name, stage)

    def find_draws_by_texture(self, texture_name):
        """Find all draw calls using a texture with the given name (partial match)"""
        return self._search.find_draws_by_texture(texture_name)

    def find_draws_by_resource(self, resource_id):
        """Find all draw calls using a specific resource ID (exact match)"""
        return self._search.find_draws_by_resource(resource_id)

    # ==================== Resource Operations ====================

    def get_buffer_contents(self, resource_id, offset=0, length=0):
        """Get buffer data"""
        return self._resource.get_buffer_contents(resource_id, offset, length)

    def get_texture_info(self, resource_id):
        """Get texture metadata"""
        return self._resource.get_texture_info(resource_id)

    def get_texture_data(self, resource_id, mip=0, slice=0, sample=0, depth_slice=None):
        """Get texture pixel data"""
        return self._resource.get_texture_data(resource_id, mip, slice, sample, depth_slice)

    # ==================== Pipeline Operations ====================

    def get_shader_info(self, event_id, stage):
        """Get shader information for a specific stage"""
        return self._pipeline.get_shader_info(event_id, stage)

    def get_pipeline_state(self, event_id):
        """Get full pipeline state at an event"""
        return self._pipeline.get_pipeline_state(event_id)

    # ==================== Shader Edit / Replay Operations ====================

    def get_shader_source(self, event_id, stage):
        """Get the raw shader bytes (and encoding) at event/stage"""
        return self._shader_edit.get_shader_source(event_id, stage)

    def compile_shader(self, hlsl, stage, entry, encoding="hlsl", compile_flags=None):
        """Compile HLSL/GLSL source into a replacement shader"""
        return self._shader_edit.compile_shader(hlsl, stage, entry, encoding, compile_flags)

    def replace_shader(self, event_id, stage, compiled_resource_id):
        """Replace the shader bound at event/stage with a compiled shader"""
        return self._shader_edit.replace_shader(event_id, stage, compiled_resource_id)

    def remove_shader_replacement(self, event_id, stage):
        """Remove any shader replacement at event/stage"""
        return self._shader_edit.remove_shader_replacement(event_id, stage)

    def replay_event(self, event_id):
        """Replay the capture up to event_id"""
        return self._shader_edit.replay_event(event_id)

    def get_debug_messages(self):
        """Retrieve newly generated diagnostic/validation messages"""
        return self._shader_edit.get_debug_messages()

    # ==================== Pixel / Mesh (human 90% toolkit) ====================

    def pick_pixel(self, event_id, x, y, resource_id=None, mip=0, slice_idx=0, sample=0):
        """Pick the numeric value of one pixel (Texture Viewer right-click)."""
        return self._pixel.pick_pixel(event_id, x, y, resource_id, mip, slice_idx, sample)

    def get_pixel_history(
        self, event_id, x, y, resource_id=None, mip=0, slice_idx=0, sample=0, max_events=32
    ):
        """Who wrote this pixel (green pass / red test-fail)."""
        return self._pixel.get_pixel_history(
            event_id, x, y, resource_id, mip, slice_idx, sample, max_events
        )

    def get_mesh_data(self, event_id, max_vertices=8):
        """Sample mesh VSIn vs VSOut (Mesh Viewer input/output)."""
        return self._mesh.get_mesh_data(event_id, max_vertices)

    def get_resource_usage(self, resource_id):
        """Events that read/write this resource (timeline strip)."""
        return self._resource.get_resource_usage(resource_id)

    def close_capture(self):
        return self._capture.close_capture()

    def save_capture(self, capture_path):
        return self._capture.save_capture(capture_path)

    def embed_dependencies(self):
        return self._capture.embed_dependencies()

    def remove_dependencies(self):
        return self._capture.remove_dependencies()

    def list_capture_formats(self):
        return self._capture.list_capture_formats()

    def convert_capture(self, filename, filetype="rdc"):
        return self._capture.convert_capture(filename, filetype)

    def set_event(self, event_id, force=True):
        return self._capture.set_event(event_id, force)

    def export_texture(self, resource_id, path=None, mip=0, slice_idx=0, sample=0, dest_type="png"):
        return self._export.export_texture(resource_id, path, mip, slice_idx, sample, dest_type)

    def export_render_target(self, event_id, path=None, target_index=0, dest_type="png"):
        return self._export.export_render_target(event_id, path, target_index, dest_type)

    def get_thumbnail(self, path=None, dest_type="png"):
        return self._export.get_thumbnail(path, dest_type)

    def export_buffer(self, resource_id, path=None, offset=0, length=0):
        return self._export.export_buffer(resource_id, path, offset, length)

    def debug_pixel(self, event_id, x, y, sample=None, primitive=None, max_steps=64, last_n=8):
        return self._debug.debug_pixel(event_id, x, y, sample, primitive, max_steps, last_n)

    def debug_vertex(self, event_id, vertex_id, instance=0, index=None, view=0, max_steps=64, last_n=8):
        return self._debug.debug_vertex(event_id, vertex_id, instance, index, view, max_steps, last_n)

    def debug_thread(self, event_id, group_x, group_y, group_z, thread_x, thread_y, thread_z, max_steps=64, last_n=8):
        return self._debug.debug_thread(
            event_id, group_x, group_y, group_z, thread_x, thread_y, thread_z, max_steps, last_n
        )

    def debug_trace_export(self, event_id, x, y, sample=None, primitive=None, path=None, max_steps=None):
        return self._debug.debug_trace_export(event_id, x, y, sample, primitive, path, max_steps)

    def list_resources(self, resource_type=None, name=None, limit=200):
        return self._resource.list_resources(resource_type, name, limit)

    def get_resource(self, resource_id):
        return self._resource.get_resource(resource_id)

    def replace_resource(self, original_resource_id, replacement_resource_id):
        return self._resource.replace_resource(original_resource_id, replacement_resource_id)

    def restore_resource(self, original_resource_id):
        return self._resource.restore_resource(original_resource_id)

    def restore_all_replacements(self):
        return self._resource.restore_all_replacements()

    def get_texture_stats(self, resource_id, event_id=None, mip=0, slice_idx=0, histogram=False):
        return self._resource.get_texture_stats(resource_id, event_id, mip, slice_idx, histogram)

    def list_shader_encodings(self):
        return self._shader_edit.list_shader_encodings()

    def list_shaders(self, stage=None, limit=200):
        return self._shader_edit.list_shaders(stage, limit)

    def shader_map(self, limit=200):
        return self._shader_edit.shader_map(limit)

    def search_shaders(self, pattern, stage=None, limit=50):
        return self._shader_edit.search_shaders(pattern, stage, limit)

    def compile_custom_shader(self, source, stage, entry, encoding="hlsl"):
        return self._shader_edit.compile_custom_shader(source, stage, entry, encoding)

    def get_counters(self, event_id=None, name_filter=None, list_only=False):
        return self._analysis.get_counters(event_id, name_filter, list_only)

    def get_snapshot(self, event_id):
        return self._analysis.get_snapshot(event_id)

    def list_sections(self):
        return self._analysis.list_sections()

    def get_section(self, index=None, name=None, max_bytes=4096):
        return self._analysis.get_section(index, name, max_bytes)

    def write_section(self, name, contents, section_type="unknown"):
        return self._analysis.write_section(name, contents, section_type)
