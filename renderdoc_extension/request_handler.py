"""
Request Handler for RenderDoc MCP Bridge
Routes incoming requests to appropriate facade methods.
"""

import traceback


class RequestHandler:
    """Handles incoming MCP bridge requests"""

    def __init__(self, facade):
        self.facade = facade
        self._methods = {
            "ping": self._handle_ping,
            "get_capture_status": self._handle_get_capture_status,
            "get_draw_calls": self._handle_get_draw_calls,
            "get_frame_summary": self._handle_get_frame_summary,
            "find_draws_by_shader": self._handle_find_draws_by_shader,
            "find_draws_by_texture": self._handle_find_draws_by_texture,
            "find_draws_by_resource": self._handle_find_draws_by_resource,
            "get_draw_call_details": self._handle_get_draw_call_details,
            "get_action_timings": self._handle_get_action_timings,
            "get_shader_info": self._handle_get_shader_info,
            "get_buffer_contents": self._handle_get_buffer_contents,
            "get_texture_info": self._handle_get_texture_info,
            "get_texture_data": self._handle_get_texture_data,
            "get_pipeline_state": self._handle_get_pipeline_state,
            "list_captures": self._handle_list_captures,
            "open_capture": self._handle_open_capture,
            "get_shader_source": self._handle_get_shader_source,
            "compile_shader": self._handle_compile_shader,
            "replace_shader": self._handle_replace_shader,
            "remove_shader_replacement": self._handle_remove_shader_replacement,
            "replay_event": self._handle_replay_event,
            "get_debug_messages": self._handle_get_debug_messages,
            "pick_pixel": self._handle_pick_pixel,
            "get_pixel_history": self._handle_get_pixel_history,
            "get_mesh_data": self._handle_get_mesh_data,
            "get_resource_usage": self._handle_get_resource_usage,
            "close_capture": self._handle_close_capture,
            "save_capture": self._handle_save_capture,
            "embed_dependencies": self._handle_embed_dependencies,
            "remove_dependencies": self._handle_remove_dependencies,
            "list_capture_formats": self._handle_list_capture_formats,
            "convert_capture": self._handle_convert_capture,
            "set_event": self._handle_set_event,
            "export_texture": self._handle_export_texture,
            "export_render_target": self._handle_export_render_target,
            "get_thumbnail": self._handle_get_thumbnail,
            "export_buffer": self._handle_export_buffer,
            "debug_pixel": self._handle_debug_pixel,
            "debug_vertex": self._handle_debug_vertex,
            "debug_thread": self._handle_debug_thread,
            "list_resources": self._handle_list_resources,
            "get_resource": self._handle_get_resource,
            "replace_resource": self._handle_replace_resource,
            "restore_resource": self._handle_restore_resource,
            "restore_all_replacements": self._handle_restore_all_replacements,
            "get_texture_stats": self._handle_get_texture_stats,
            "list_shader_encodings": self._handle_list_shader_encodings,
            "list_shaders": self._handle_list_shaders,
            "shader_map": self._handle_shader_map,
            "search_shaders": self._handle_search_shaders,
            "compile_custom_shader": self._handle_compile_custom_shader,
            "get_counters": self._handle_get_counters,
            "get_snapshot": self._handle_get_snapshot,
            "list_sections": self._handle_list_sections,
            "get_section": self._handle_get_section,
            "write_section": self._handle_write_section,
        }

    def handle(self, request):
        """Handle a request and return response"""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        try:
            if method not in self._methods:
                return self._error_response(
                    request_id, -32601, "Method not found: %s" % method
                )

            result = self._methods[method](params)
            return {"id": request_id, "result": result}

        except ValueError as e:
            return self._error_response(request_id, -32602, str(e))
        except Exception as e:
            traceback.print_exc()
            return self._error_response(request_id, -32000, str(e))

    def _error_response(self, request_id, code, message):
        """Create an error response"""
        return {"id": request_id, "error": {"code": code, "message": message}}

    def _handle_ping(self, params):
        """Handle ping request"""
        return {"status": "ok", "message": "pong"}

    def _handle_get_capture_status(self, params):
        """Handle get_capture_status request"""
        return self.facade.get_capture_status()

    def _handle_get_draw_calls(self, params):
        """Handle get_draw_calls request"""
        include_children = params.get("include_children", True)
        marker_filter = params.get("marker_filter")
        exclude_markers = params.get("exclude_markers")
        event_id_min = params.get("event_id_min")
        event_id_max = params.get("event_id_max")
        only_actions = params.get("only_actions", False)
        flags_filter = params.get("flags_filter")
        preset = params.get("preset")
        return self.facade.get_draw_calls(
            include_children=include_children,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
            event_id_min=event_id_min,
            event_id_max=event_id_max,
            only_actions=only_actions,
            flags_filter=flags_filter,
            preset=preset,
        )

    def _handle_get_frame_summary(self, params):
        """Handle get_frame_summary request"""
        return self.facade.get_frame_summary()

    def _handle_find_draws_by_shader(self, params):
        """Handle find_draws_by_shader request"""
        shader_name = params.get("shader_name")
        if shader_name is None:
            raise ValueError("shader_name is required")
        stage = params.get("stage")
        return self.facade.find_draws_by_shader(shader_name, stage)

    def _handle_find_draws_by_texture(self, params):
        """Handle find_draws_by_texture request"""
        texture_name = params.get("texture_name")
        if texture_name is None:
            raise ValueError("texture_name is required")
        return self.facade.find_draws_by_texture(texture_name)

    def _handle_find_draws_by_resource(self, params):
        """Handle find_draws_by_resource request"""
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.find_draws_by_resource(resource_id)

    def _handle_get_draw_call_details(self, params):
        """Handle get_draw_call_details request"""
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.get_draw_call_details(int(event_id))

    def _handle_get_action_timings(self, params):
        """Handle get_action_timings request"""
        event_ids = params.get("event_ids")
        marker_filter = params.get("marker_filter")
        exclude_markers = params.get("exclude_markers")
        return self.facade.get_action_timings(
            event_ids=event_ids,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
        )

    def _handle_get_shader_info(self, params):
        """Handle get_shader_info request"""
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None:
            raise ValueError("event_id is required")
        if stage is None:
            raise ValueError("stage is required")
        return self.facade.get_shader_info(int(event_id), stage)

    def _handle_get_buffer_contents(self, params):
        """Handle get_buffer_contents request"""
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        offset = params.get("offset", 0)
        length = params.get("length", 0)
        return self.facade.get_buffer_contents(resource_id, offset, length)

    def _handle_get_texture_info(self, params):
        """Handle get_texture_info request"""
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.get_texture_info(resource_id)

    def _handle_get_texture_data(self, params):
        """Handle get_texture_data request"""
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        mip = params.get("mip", 0)
        slice_idx = params.get("slice", 0)
        sample = params.get("sample", 0)
        depth_slice = params.get("depth_slice")  # None = full volume
        return self.facade.get_texture_data(resource_id, mip, slice_idx, sample, depth_slice)

    def _handle_get_pipeline_state(self, params):
        """Handle get_pipeline_state request"""
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.get_pipeline_state(int(event_id))

    def _handle_list_captures(self, params):
        """Handle list_captures request"""
        directory = params.get("directory")
        if directory is None:
            raise ValueError("directory is required")
        return self.facade.list_captures(directory)

    def _handle_open_capture(self, params):
        """Handle open_capture request"""
        capture_path = params.get("capture_path")
        if capture_path is None:
            raise ValueError("capture_path is required")
        return self.facade.open_capture(capture_path)

    def _handle_get_shader_source(self, params):
        """Handle get_shader_source request"""
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None:
            raise ValueError("event_id is required")
        if stage is None:
            raise ValueError("stage is required")
        return self.facade.get_shader_source(int(event_id), stage)

    def _handle_compile_shader(self, params):
        """Handle compile_shader request"""
        hlsl = params.get("hlsl")
        stage = params.get("stage")
        entry = params.get("entry")
        if hlsl is None:
            raise ValueError("hlsl is required")
        if stage is None:
            raise ValueError("stage is required")
        if entry is None:
            raise ValueError("entry is required")
        encoding = params.get("encoding", "hlsl")
        compile_flags = params.get("compile_flags")
        return self.facade.compile_shader(hlsl, stage, entry, encoding, compile_flags)

    def _handle_replace_shader(self, params):
        """Handle replace_shader request"""
        event_id = params.get("event_id")
        stage = params.get("stage")
        compiled_resource_id = params.get("compiled_resource_id")
        if event_id is None:
            raise ValueError("event_id is required")
        if stage is None:
            raise ValueError("stage is required")
        if compiled_resource_id is None:
            raise ValueError("compiled_resource_id is required")
        return self.facade.replace_shader(int(event_id), stage, compiled_resource_id)

    def _handle_remove_shader_replacement(self, params):
        """Handle remove_shader_replacement request"""
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None:
            raise ValueError("event_id is required")
        if stage is None:
            raise ValueError("stage is required")
        return self.facade.remove_shader_replacement(int(event_id), stage)

    def _handle_replay_event(self, params):
        """Handle replay_event request"""
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.replay_event(int(event_id))

    def _handle_get_debug_messages(self, params):
        """Handle get_debug_messages request"""
        return self.facade.get_debug_messages()

    def _handle_pick_pixel(self, params):
        event_id = params.get("event_id")
        x = params.get("x")
        y = params.get("y")
        if event_id is None:
            raise ValueError("event_id is required")
        if x is None or y is None:
            raise ValueError("x and y are required")
        return self.facade.pick_pixel(
            int(event_id),
            int(x),
            int(y),
            resource_id=params.get("resource_id"),
            mip=params.get("mip", 0),
            slice_idx=params.get("slice", 0),
            sample=params.get("sample", 0),
        )

    def _handle_get_pixel_history(self, params):
        event_id = params.get("event_id")
        x = params.get("x")
        y = params.get("y")
        if event_id is None:
            raise ValueError("event_id is required")
        if x is None or y is None:
            raise ValueError("x and y are required")
        return self.facade.get_pixel_history(
            int(event_id),
            int(x),
            int(y),
            resource_id=params.get("resource_id"),
            mip=params.get("mip", 0),
            slice_idx=params.get("slice", 0),
            sample=params.get("sample", 0),
            max_events=params.get("max_events", 32),
        )

    def _handle_get_mesh_data(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.get_mesh_data(
            int(event_id), max_vertices=params.get("max_vertices", 8)
        )

    def _handle_get_resource_usage(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.get_resource_usage(resource_id)

    def _handle_close_capture(self, params):
        return self.facade.close_capture()

    def _handle_save_capture(self, params):
        capture_path = params.get("capture_path")
        if not capture_path:
            raise ValueError("capture_path is required")
        return self.facade.save_capture(capture_path)

    def _handle_embed_dependencies(self, params):
        return self.facade.embed_dependencies()

    def _handle_remove_dependencies(self, params):
        return self.facade.remove_dependencies()

    def _handle_list_capture_formats(self, params):
        return self.facade.list_capture_formats()

    def _handle_convert_capture(self, params):
        filename = params.get("filename")
        if not filename:
            raise ValueError("filename is required")
        return self.facade.convert_capture(
            filename, filetype=params.get("filetype", "rdc")
        )

    def _handle_set_event(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        force = params.get("force", True)
        return self.facade.set_event(int(event_id), force)

    def _handle_export_texture(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.export_texture(
            resource_id,
            path=params.get("path"),
            mip=params.get("mip", 0),
            slice_idx=params.get("slice", 0),
            sample=params.get("sample", 0),
            dest_type=params.get("dest_type", "png"),
        )

    def _handle_export_render_target(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.export_render_target(
            int(event_id),
            path=params.get("path"),
            target_index=params.get("target_index", 0),
            dest_type=params.get("dest_type", "png"),
        )

    def _handle_get_thumbnail(self, params):
        return self.facade.get_thumbnail(
            path=params.get("path"),
            dest_type=params.get("dest_type", "png"),
        )

    def _handle_export_buffer(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.export_buffer(
            resource_id,
            path=params.get("path"),
            offset=params.get("offset", 0),
            length=params.get("length", 0),
        )

    def _handle_debug_pixel(self, params):
        event_id = params.get("event_id")
        x = params.get("x")
        y = params.get("y")
        if event_id is None:
            raise ValueError("event_id is required")
        if x is None or y is None:
            raise ValueError("x and y are required")
        return self.facade.debug_pixel(
            int(event_id),
            int(x),
            int(y),
            sample=params.get("sample"),
            primitive=params.get("primitive"),
            max_steps=params.get("max_steps", 64),
            last_n=params.get("last_n", 8),
        )

    def _handle_debug_vertex(self, params):
        event_id = params.get("event_id")
        vertex_id = params.get("vertex_id")
        if event_id is None:
            raise ValueError("event_id is required")
        if vertex_id is None:
            raise ValueError("vertex_id is required")
        return self.facade.debug_vertex(
            int(event_id),
            int(vertex_id),
            instance=params.get("instance", 0),
            index=params.get("index"),
            view=params.get("view", 0),
            max_steps=params.get("max_steps", 64),
            last_n=params.get("last_n", 8),
        )

    def _handle_debug_thread(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        for key in ("group_x", "group_y", "group_z", "thread_x", "thread_y", "thread_z"):
            if params.get(key) is None:
                raise ValueError("%s is required" % key)
        return self.facade.debug_thread(
            int(event_id),
            int(params["group_x"]),
            int(params["group_y"]),
            int(params["group_z"]),
            int(params["thread_x"]),
            int(params["thread_y"]),
            int(params["thread_z"]),
            max_steps=params.get("max_steps", 64),
            last_n=params.get("last_n", 8),
        )

    def _handle_list_resources(self, params):
        return self.facade.list_resources(
            resource_type=params.get("resource_type"),
            name=params.get("name"),
            limit=params.get("limit", 200),
        )

    def _handle_get_resource(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.get_resource(resource_id)

    def _handle_replace_resource(self, params):
        original = params.get("original_resource_id")
        replacement = params.get("replacement_resource_id")
        if original is None or replacement is None:
            raise ValueError("original_resource_id and replacement_resource_id are required")
        return self.facade.replace_resource(original, replacement)

    def _handle_restore_resource(self, params):
        resource_id = params.get("original_resource_id") or params.get("resource_id")
        if resource_id is None:
            raise ValueError("original_resource_id is required")
        return self.facade.restore_resource(resource_id)

    def _handle_restore_all_replacements(self, params):
        return self.facade.restore_all_replacements()

    def _handle_get_texture_stats(self, params):
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.get_texture_stats(
            resource_id,
            event_id=params.get("event_id"),
            mip=params.get("mip", 0),
            slice_idx=params.get("slice", 0),
            histogram=params.get("histogram", False),
        )

    def _handle_list_shader_encodings(self, params):
        return self.facade.list_shader_encodings()

    def _handle_list_shaders(self, params):
        return self.facade.list_shaders(
            stage=params.get("stage"),
            limit=params.get("limit", 200),
        )

    def _handle_shader_map(self, params):
        return self.facade.shader_map(limit=params.get("limit", 200))

    def _handle_search_shaders(self, params):
        pattern = params.get("pattern")
        if not pattern:
            raise ValueError("pattern is required")
        return self.facade.search_shaders(
            pattern,
            stage=params.get("stage"),
            limit=params.get("limit", 50),
        )

    def _handle_compile_custom_shader(self, params):
        source = params.get("source") or params.get("hlsl")
        stage = params.get("stage")
        entry = params.get("entry")
        if source is None:
            raise ValueError("source is required")
        if stage is None:
            raise ValueError("stage is required")
        if entry is None:
            raise ValueError("entry is required")
        return self.facade.compile_custom_shader(
            source, stage, entry, encoding=params.get("encoding", "hlsl")
        )

    def _handle_get_counters(self, params):
        return self.facade.get_counters(
            event_id=params.get("event_id"),
            name_filter=params.get("name_filter"),
            list_only=params.get("list_only", False),
        )

    def _handle_get_snapshot(self, params):
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.get_snapshot(int(event_id))

    def _handle_list_sections(self, params):
        return self.facade.list_sections()

    def _handle_get_section(self, params):
        index = params.get("index")
        name = params.get("name")
        if index is None and not name:
            raise ValueError("index or name is required")
        return self.facade.get_section(
            index=index,
            name=name,
            max_bytes=params.get("max_bytes", 4096),
        )

    def _handle_write_section(self, params):
        name = params.get("name")
        contents = params.get("contents")
        if not name:
            raise ValueError("name is required")
        if contents is None:
            raise ValueError("contents is required")
        return self.facade.write_section(
            name,
            contents,
            section_type=params.get("section_type", "unknown"),
        )
