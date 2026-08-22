"""
RenderDoc MCP Server
FastMCP 2.0 server providing access to RenderDoc capture data.
"""

from typing import Literal

from fastmcp import FastMCP

from .bridge.client import RenderDocBridge, RenderDocBridgeError
from .cache import MemoryBackend, OpenVikingBackend, ResponseCache
from .config import settings

# Initialize FastMCP server
mcp = FastMCP(
    name="RenderDoc MCP Server",
)

# RenderDoc bridge client, optionally wrapped in a read-through response cache.
_bridge = RenderDocBridge(host=settings.renderdoc_host, port=settings.renderdoc_port)
if settings.cache_enabled:
    if settings.cache_backend in ("openviking", "ov"):
        try:
            backend = OpenVikingBackend()
        except Exception:
            backend = MemoryBackend()
    else:
        backend = MemoryBackend()
    bridge = ResponseCache(
        _bridge,
        backend=backend,
        max_entry_bytes=settings.cache_max_entry_bytes,
    )
else:
    bridge = _bridge


@mcp.tool
def get_capture_status() -> dict:
    """
    Check if a capture is currently loaded in RenderDoc.
    Returns the capture status and API type if loaded.
    """
    return bridge.call("get_capture_status")


@mcp.tool
def get_draw_calls(
    include_children: bool = True,
    marker_filter: str | None = None,
    exclude_markers: list[str] | None = None,
    event_id_min: int | None = None,
    event_id_max: int | None = None,
    only_actions: bool = False,
    flags_filter: list[str] | None = None,
    preset: Literal["unity_game_rendering"] | None = None,
) -> dict:
    """
    Get the list of all draw calls and actions in the current capture.

    Args:
        include_children: Include child actions in the hierarchy (default: True)
        marker_filter: Only include actions under markers containing this string (partial match)
        exclude_markers: Exclude actions under markers containing these strings (list of partial matches)
        event_id_min: Only include actions with event_id >= this value
        event_id_max: Only include actions with event_id <= this value
        only_actions: If True, exclude marker actions (PushMarker/PopMarker/SetMarker)
        flags_filter: Only include actions with these flags (list of flag names, e.g. ["Drawcall", "Dispatch"])
        preset: Named filter. "unity_game_rendering" keeps Camera.Render and drops
                editor UI (GUI.Repaint, UIR.DrawChain, EditorLoop, ...). Prefer this
                on Unity Editor captures instead of dumping the whole frame.

    Returns a hierarchical tree of actions including markers, draw calls,
    dispatches, and other GPU events.
    """
    params: dict[str, object] = {"include_children": include_children}
    if marker_filter is not None:
        params["marker_filter"] = marker_filter
    if exclude_markers is not None:
        params["exclude_markers"] = exclude_markers
    if event_id_min is not None:
        params["event_id_min"] = event_id_min
    if event_id_max is not None:
        params["event_id_max"] = event_id_max
    if only_actions:
        params["only_actions"] = only_actions
    if flags_filter is not None:
        params["flags_filter"] = flags_filter
    if preset is not None:
        params["preset"] = preset
    return bridge.call("get_draw_calls", params)


@mcp.tool
def get_frame_summary() -> dict:
    """
    Get a summary of the current capture frame.

    Returns statistics about the frame including:
    - API type (D3D11, D3D12, Vulkan, etc.)
    - Total action count
    - Statistics: draw calls, dispatches, clears, copies, presents, markers
    - Top-level markers with event IDs and child counts
    - Resource counts: textures, buffers
    """
    return bridge.call("get_frame_summary")


@mcp.tool
def find_draws_by_shader(
    shader_name: str,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"] | None = None,
) -> dict:
    """
    Find all draw calls using a shader with the given name (partial match).

    Args:
        shader_name: Partial name to search for in shader names or entry points
        stage: Optional shader stage to search (if not specified, searches all stages)

    Returns a list of matching draw calls with event IDs and match reasons.
    """
    params: dict[str, object] = {"shader_name": shader_name}
    if stage is not None:
        params["stage"] = stage
    return bridge.call("find_draws_by_shader", params)


@mcp.tool
def find_draws_by_texture(texture_name: str) -> dict:
    """
    Find all draw calls using a texture with the given name (partial match).

    Args:
        texture_name: Partial name to search for in texture resource names

    Returns a list of matching draw calls with event IDs and match reasons.
    Searches SRVs, UAVs, and render targets.
    """
    return bridge.call("find_draws_by_texture", {"texture_name": texture_name})


@mcp.tool
def find_draws_by_resource(resource_id: str) -> dict:
    """
    Find all draw calls using a specific resource ID (exact match).

    Args:
        resource_id: Resource ID to search for (e.g. "ResourceId::12345" or "12345")

    Returns a list of matching draw calls with event IDs and match reasons.
    Searches shaders, SRVs, UAVs, render targets, and depth targets.
    """
    return bridge.call("find_draws_by_resource", {"resource_id": resource_id})


@mcp.tool
def get_draw_call_details(event_id: int) -> dict:
    """
    Get detailed information about a specific draw call.

    Args:
        event_id: The event ID of the draw call to inspect

    Includes vertex/index counts, resource outputs, and other metadata.
    """
    return bridge.call("get_draw_call_details", {"event_id": event_id})


@mcp.tool
def get_action_timings(
    event_ids: list[int] | None = None,
    marker_filter: str | None = None,
    exclude_markers: list[str] | None = None,
) -> dict:
    """
    Get GPU timing information for actions (draw calls, dispatches, etc.).

    Args:
        event_ids: Optional list of specific event IDs to get timings for.
                   If not specified, returns timings for all actions.
        marker_filter: Only include actions under markers containing this string (partial match).
        exclude_markers: Exclude actions under markers containing these strings.

    Returns timing data including:
    - available: Whether GPU timing counters are supported
    - unit: Time unit (typically "seconds")
    - timings: List of {event_id, name, duration_seconds, duration_ms}
    - total_duration_ms: Sum of all durations
    - count: Number of timing entries

    Note: GPU timing counters may not be available on all hardware/drivers.
    """
    params: dict[str, object] = {}
    if event_ids is not None:
        params["event_ids"] = event_ids
    if marker_filter is not None:
        params["marker_filter"] = marker_filter
    if exclude_markers is not None:
        params["exclude_markers"] = exclude_markers
    return bridge.call("get_action_timings", params)


@mcp.tool
def get_shader_info(
    event_id: int,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"],
) -> dict:
    """
    Get shader information for a specific stage at a given event.

    Args:
        event_id: The event ID to inspect the shader at
        stage: The shader stage (vertex, hull, domain, geometry, pixel, compute)

    Returns shader disassembly, constant buffer values, and resource bindings.
    """
    return bridge.call("get_shader_info", {"event_id": event_id, "stage": stage})


@mcp.tool
def get_buffer_contents(
    resource_id: str,
    offset: int = 0,
    length: int = 0,
) -> dict:
    """
    Read the contents of a buffer resource.

    Args:
        resource_id: The resource ID of the buffer to read
        offset: Byte offset to start reading from (default: 0)
        length: Number of bytes to read, 0 for entire buffer (default: 0)

    Returns buffer data as base64-encoded bytes along with metadata.
    """
    return bridge.call(
        "get_buffer_contents",
        {"resource_id": resource_id, "offset": offset, "length": length},
    )


@mcp.tool
def get_texture_info(resource_id: str) -> dict:
    """
    Get metadata about a texture resource.

    Args:
        resource_id: The resource ID of the texture

    Includes dimensions, format, mip levels, and other properties.
    """
    return bridge.call("get_texture_info", {"resource_id": resource_id})


@mcp.tool
def get_texture_data(
    resource_id: str,
    mip: int = 0,
    slice: int = 0,
    sample: int = 0,
    depth_slice: int | None = None,
) -> dict:
    """
    Read the pixel data of a texture resource.

    Args:
        resource_id: The resource ID of the texture to read
        mip: Mip level to retrieve (default: 0)
        slice: Array slice or cube face index (default: 0)
               For cube maps: 0=X+, 1=X-, 2=Y+, 3=Y-, 4=Z+, 5=Z-
        sample: MSAA sample index (default: 0)
        depth_slice: For 3D textures only, extract a specific depth slice (default: None = full volume)
                     When specified, returns only the 2D slice at that depth index

    Returns texture pixel data as base64-encoded bytes along with metadata
    including dimensions at the requested mip level and format information.
    """
    params = {"resource_id": resource_id, "mip": mip, "slice": slice, "sample": sample}
    if depth_slice is not None:
        params["depth_slice"] = depth_slice
    return bridge.call("get_texture_data", params)


@mcp.tool
def get_pipeline_state(event_id: int) -> dict:
    """
    Get the full graphics pipeline state at a specific event.

    Args:
        event_id: The event ID to get pipeline state at

    Returns detailed pipeline state including:
    - Bound shaders with entry points for each stage
    - Shader resources (SRVs): textures and buffers with dimensions, format, slot, name
    - UAVs (RWTextures/RWBuffers): resource details with dimensions and format
    - Samplers: addressing modes, filter settings, LOD parameters
    - Constant buffers: slot, size, variable count
    - Render targets and depth target
    - Viewports and input assembly state
    - rasterizer (cull/fill/front_ccw, viewport, scissor)
    - depth_stencil (depth_enable/writes/function)
    - blend (per-target enabled, write_mask, color/alpha equations)
    """
    return bridge.call("get_pipeline_state", {"event_id": event_id})


@mcp.tool
def list_captures(directory: str) -> dict:
    """
    List all RenderDoc capture files (.rdc) in the specified directory.

    Args:
        directory: The directory path to search for capture files

    Returns a list of capture files with their metadata including:
    - filename: The capture file name
    - path: Full path to the file
    - size_bytes: File size in bytes
    - modified_time: Last modified timestamp (ISO format)
    """
    return bridge.call("list_captures", {"directory": directory})


@mcp.tool
def open_capture(capture_path: str) -> dict:
    """
    Open a RenderDoc capture file (.rdc).

    Args:
        capture_path: Full path to the capture file to open

    Returns success status and information about the opened capture.
    Note: This will close any currently open capture.
    """
    return bridge.call("open_capture", {"capture_path": capture_path})


@mcp.tool
def get_shader_source(
    event_id: int,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"],
) -> dict:
    """
    Get the raw shader bytes of the shader bound at an event/stage.

    Args:
        event_id: The event ID to inspect
        stage: The shader stage

    Returns the shader resource id, entry point, encoding, and (when available)
    the raw shader bytes as base64. `is_source_text` is True only when the
    encoding is directly editable (HLSL/GLSL/SPIRVAsm); binary encodings
    (DXBC/DXIL/SPIRV) are not editable source.
    """
    return bridge.call("get_shader_source", {"event_id": event_id, "stage": stage})


@mcp.tool
def compile_shader(
    hlsl: str,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"],
    entry: str,
    encoding: Literal["hlsl", "glsl", "spirv", "dxbc", "dxil"] = "hlsl",
    compile_flags: Literal["default", "debug"] = "default",
) -> dict:
    """
    Compile shader source into a replacement shader for the capture's API.

    Args:
        hlsl: The shader source (HLSL/GLSL/etc. depending on encoding)
        stage: The shader stage this source is for
        entry: The entry point function name (e.g. "main", "PSMain")
        encoding: The source encoding (default "hlsl")
        compile_flags: "default" (empty flags) or "debug"
            (D3DCOMPILE_DEBUG + D3DCOMPILE_SKIP_OPTIMIZATION). Use "debug"
            when you need source-level debug_pixel stepping.

    Returns the compiled shader's resource id and any compiler messages.
    Raises an error if compilation fails.
    """
    return bridge.call(
        "compile_shader",
        {
            "hlsl": hlsl,
            "stage": stage,
            "entry": entry,
            "encoding": encoding,
            "compile_flags": compile_flags,
        },
    )


@mcp.tool
def replace_shader(
    event_id: int,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"],
    compiled_resource_id: str,
) -> dict:
    """
    Replace the shader bound at an event/stage with a previously compiled shader.

    Args:
        event_id: The event ID where the shader is bound
        stage: The shader stage to replace
        compiled_resource_id: The resource id returned by compile_shader

    Returns the original and replacement resource ids.
    """
    return bridge.call(
        "replace_shader",
        {"event_id": event_id, "stage": stage, "compiled_resource_id": compiled_resource_id},
    )


@mcp.tool
def remove_shader_replacement(
    event_id: int,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"],
) -> dict:
    """
    Remove any shader replacement at an event/stage, restoring the original.

    Args:
        event_id: The event ID where the replacement was applied
        stage: The shader stage to restore
    """
    return bridge.call(
        "remove_shader_replacement", {"event_id": event_id, "stage": stage}
    )


@mcp.tool
def replay_event(event_id: int) -> dict:
    """
    Replay the capture up to the given event, applying any shader replacements.

    Args:
        event_id: The event ID to replay up to
    """
    return bridge.call("replay_event", {"event_id": event_id})


@mcp.tool
def get_debug_messages() -> dict:
    """
    Retrieve newly generated diagnostic/validation messages from the last replay.

    These are the L1 deterministic validation-layer messages (RenderDoc's
    GetDebugMessages). Each call drains the queue of new messages.
    """
    return bridge.call("get_debug_messages")


@mcp.tool
def pick_pixel(
    event_id: int,
    x: int,
    y: int,
    resource_id: str | None = None,
    mip: int = 0,
    slice: int = 0,
    sample: int = 0,
) -> dict:
    """
    Read one pixel (Texture Viewer right-click). Prefer this over get_texture_data.

    Coordinates are top-left origin even on OpenGL. If resource_id is omitted,
    uses the first color target of the action at event_id.
    """
    params: dict[str, object] = {
        "event_id": event_id,
        "x": x,
        "y": y,
        "mip": mip,
        "slice": slice,
        "sample": sample,
    }
    if resource_id is not None:
        params["resource_id"] = resource_id
    return bridge.call("pick_pixel", params)


@mcp.tool
def get_pixel_history(
    event_id: int,
    x: int,
    y: int,
    resource_id: str | None = None,
    mip: int = 0,
    slice: int = 0,
    sample: int = 0,
    max_events: int = 32,
) -> dict:
    """
    Who wrote this pixel (Pixel History). First tool for "this pixel is wrong".

    Each event has passed=true/false and failed.depth/stencil/backface/scissor/
    shader_discard. Debug the last *passing* fragment, not a full shader trace.
    Caps at max_events (default 32). Can be slow or unsupported on some GPUs.
    """
    params: dict[str, object] = {
        "event_id": event_id,
        "x": x,
        "y": y,
        "mip": mip,
        "slice": slice,
        "sample": sample,
        "max_events": max_events,
    }
    if resource_id is not None:
        params["resource_id"] = resource_id
    return bridge.call("get_pixel_history", params)


@mcp.tool
def get_mesh_data(event_id: int, max_vertices: int = 8) -> dict:
    """
    Sample mesh input vs vertex-shader output (Mesh Viewer).

    First tool for "the mesh looks wrong": if input vertices/indices are already
    bad (degenerate IDX like 5,6,6), it is not a shader bug. Default 8 vertices.
    """
    return bridge.call(
        "get_mesh_data", {"event_id": event_id, "max_vertices": max_vertices}
    )


@mcp.tool
def get_resource_usage(resource_id: str) -> dict:
    """
    Events that read or write this resource (timeline / Texture Viewer usage strip).
    """
    return bridge.call("get_resource_usage", {"resource_id": resource_id})


@mcp.tool
def close_capture() -> dict:
    """Close the currently loaded capture. No-op if none is loaded."""
    return bridge.call("close_capture")


@mcp.tool
def save_capture(capture_path: str) -> dict:
    """
    Save the loaded capture (including shader/resource replacements) to a new .rdc.

    Args:
        capture_path: Destination path for the saved capture.
    """
    return bridge.call("save_capture", {"capture_path": capture_path})


@mcp.tool
def embed_dependencies() -> dict:
    """Embed shader-debug files into the capture (EmbedDependenciesIntoCapture).

    Makes debug_pixel/vertex/thread portable after the capture leaves this machine.
    Call save_capture to persist a copy.
    """
    return bridge.call("embed_dependencies")


@mcp.tool
def remove_dependencies() -> dict:
    """Remove previously embedded shader-debug files from the capture."""
    return bridge.call("remove_dependencies")


@mcp.tool
def list_capture_formats() -> dict:
    """List CaptureFile formats this RenderDoc build can open or convert to."""
    return bridge.call("list_capture_formats")


@mcp.tool
def convert_capture(filename: str, filetype: str = "rdc") -> dict:
    """Export/convert the open capture to another representation on disk.

    Args:
        filename: Destination path.
        filetype: Format extension from list_capture_formats (default "rdc").
    """
    return bridge.call(
        "convert_capture", {"filename": filename, "filetype": filetype}
    )


@mcp.tool
def set_event(event_id: int, force: bool = True) -> dict:
    """
    Jump the RenderDoc UI (Texture Viewer, Pipeline, Mesh Viewer) to event_id.

    Unlike replay_event this is a CaptureContext.SetEventID call: the UI follows.
    """
    return bridge.call("set_event", {"event_id": event_id, "force": force})


@mcp.tool
def export_texture(
    resource_id: str,
    path: str | None = None,
    mip: int = 0,
    slice: int = 0,
    sample: int = 0,
    dest_type: Literal["png", "jpg", "bmp", "tga", "hdr", "exr", "raw", "dds"] = "png",
) -> dict:
    """
    Save a texture to disk via ReplayController.SaveTexture.

    Returns {path, width, height, format} — never the image bytes in JSON.
    If path is omitted, writes under %TEMP%/renderdoc_mcp/exports/.
    """
    params: dict[str, object] = {
        "resource_id": resource_id,
        "mip": mip,
        "slice": slice,
        "sample": sample,
        "dest_type": dest_type,
    }
    if path is not None:
        params["path"] = path
    return bridge.call("export_texture", params)


@mcp.tool
def export_render_target(
    event_id: int,
    path: str | None = None,
    target_index: int = 0,
    dest_type: Literal["png", "jpg", "bmp", "tga", "hdr", "exr", "raw", "dds"] = "png",
) -> dict:
    """Export the color target of an event as an image file (PNG by default)."""
    params: dict[str, object] = {
        "event_id": event_id,
        "target_index": target_index,
        "dest_type": dest_type,
    }
    if path is not None:
        params["path"] = path
    return bridge.call("export_render_target", params)


@mcp.tool
def get_thumbnail(
    path: str | None = None,
    dest_type: Literal["png", "jpg", "bmp", "tga"] = "png",
) -> dict:
    """Cheap first look: last present/draw color target saved as an image file."""
    params: dict[str, object] = {"dest_type": dest_type}
    if path is not None:
        params["path"] = path
    return bridge.call("get_thumbnail", params)


@mcp.tool
def export_buffer(
    resource_id: str,
    path: str | None = None,
    offset: int = 0,
    length: int = 0,
) -> dict:
    """Write buffer bytes to a file. Response is the path, never the bytes in JSON."""
    params: dict[str, object] = {
        "resource_id": resource_id,
        "offset": offset,
        "length": length,
    }
    if path is not None:
        params["path"] = path
    return bridge.call("export_buffer", params)


@mcp.tool
def debug_pixel(
    event_id: int,
    x: int,
    y: int,
    sample: int | None = None,
    primitive: int | None = None,
    max_steps: int = 64,
    last_n: int = 8,
) -> dict:
    """
    Pixel shader step-debug (capped JSON, never a full ISA dump).

    Caps at max_steps (default 64, hard 256) and returns last_n states.
    Bridge timeout is 120s for this call. Always FreeTrace on the extension.
    """
    params: dict[str, object] = {
        "event_id": event_id,
        "x": x,
        "y": y,
        "max_steps": max_steps,
        "last_n": last_n,
    }
    if sample is not None:
        params["sample"] = sample
    if primitive is not None:
        params["primitive"] = primitive
    return bridge.call("debug_pixel", params)


@mcp.tool
def debug_vertex(
    event_id: int,
    vertex_id: int,
    instance: int = 0,
    index: int | None = None,
    view: int = 0,
    max_steps: int = 64,
    last_n: int = 8,
) -> dict:
    """Vertex shader step-debug. Same cap / 120s timeout as debug_pixel."""
    params: dict[str, object] = {
        "event_id": event_id,
        "vertex_id": vertex_id,
        "instance": instance,
        "view": view,
        "max_steps": max_steps,
        "last_n": last_n,
    }
    if index is not None:
        params["index"] = index
    return bridge.call("debug_vertex", params)


@mcp.tool
def debug_thread(
    event_id: int,
    group_x: int,
    group_y: int,
    group_z: int,
    thread_x: int,
    thread_y: int,
    thread_z: int,
    max_steps: int = 64,
    last_n: int = 8,
) -> dict:
    """Compute shader step-debug for one thread. Same cap / 120s timeout as debug_pixel."""
    return bridge.call(
        "debug_thread",
        {
            "event_id": event_id,
            "group_x": group_x,
            "group_y": group_y,
            "group_z": group_z,
            "thread_x": thread_x,
            "thread_y": thread_y,
            "thread_z": thread_z,
            "max_steps": max_steps,
            "last_n": last_n,
        },
    )


@mcp.tool
def list_resources(
    resource_type: str | None = None,
    name: str | None = None,
    limit: int = 200,
) -> dict:
    """Catalog capture resources (id / type / name). Cap 2000."""
    params: dict[str, object] = {"limit": limit}
    if resource_type is not None:
        params["resource_type"] = resource_type
    if name is not None:
        params["name"] = name
    return bridge.call("list_resources", params)


@mcp.tool
def get_resource(resource_id: str) -> dict:
    """Resource metadata, including whether it currently has a replacement."""
    return bridge.call("get_resource", {"resource_id": resource_id})


@mcp.tool
def replace_resource(original_resource_id: str, replacement_resource_id: str) -> dict:
    """Swap one capture resource for another already in the capture.

    Applies ReplayController.ReplaceResource and CaptureContext.RegisterReplacement
    so the swap is UI-visible and persistable via save_capture. There is no
    SetTextureData/SetBufferData — swap ResourceIds (or a compiled shader) only.
    """
    return bridge.call(
        "replace_resource",
        {
            "original_resource_id": original_resource_id,
            "replacement_resource_id": replacement_resource_id,
        },
    )


@mcp.tool
def restore_resource(original_resource_id: str) -> dict:
    """Remove one resource replacement, restoring the original."""
    return bridge.call(
        "restore_resource", {"original_resource_id": original_resource_id}
    )


@mcp.tool
def restore_all_replacements() -> dict:
    """Remove every registered resource replacement in the loaded capture."""
    return bridge.call("restore_all_replacements")


@mcp.tool
def get_texture_stats(
    resource_id: str,
    event_id: int | None = None,
    mip: int = 0,
    slice: int = 0,
    histogram: bool = False,
) -> dict:
    """Per-channel min/max via GPU GetMinMax (format-aware). Optional 16-bucket histogram.

    Never reads texture bytes into Python. HDR/NaN shows up in `anomalies`, not as
    byte-noise min/max. Prefer pick_pixel for a single pixel.
    """
    params: dict[str, object] = {
        "resource_id": resource_id,
        "mip": mip,
        "slice": slice,
        "histogram": histogram,
    }
    if event_id is not None:
        params["event_id"] = event_id
    return bridge.call("get_texture_stats", params)


@mcp.tool
def list_shader_encodings() -> dict:
    """Target + custom shader encodings supported by this capture/API."""
    return bridge.call("list_shader_encodings")


@mcp.tool
def list_shaders(
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"] | None = None,
    limit: int = 200,
) -> dict:
    """Unique shaders bound in the frame, with the event ids that use them."""
    params: dict[str, object] = {"limit": limit}
    if stage is not None:
        params["stage"] = stage
    return bridge.call("list_shaders", params)


@mcp.tool
def shader_map(limit: int = 200) -> dict:
    """Event × stage → shader resource id map (token-capped)."""
    return bridge.call("shader_map", {"limit": limit})


@mcp.tool
def search_shaders(
    pattern: str,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"] | None = None,
    limit: int = 50,
) -> dict:
    """Search shader disassembly for a substring. Returns short snippets, not full ISA."""
    params: dict[str, object] = {"pattern": pattern, "limit": limit}
    if stage is not None:
        params["stage"] = stage
    return bridge.call("search_shaders", params)


@mcp.tool
def compile_custom_shader(
    source: str,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"],
    entry: str,
    encoding: Literal["hlsl", "glsl", "spirv", "dxbc", "dxil"] = "hlsl",
) -> dict:
    """BuildCustomShader — visualization shader, not a target replacement."""
    return bridge.call(
        "compile_custom_shader",
        {"source": source, "stage": stage, "entry": entry, "encoding": encoding},
    )


@mcp.tool
def get_counters(
    event_id: int | None = None,
    name_filter: str | None = None,
    list_only: bool = False,
) -> dict:
    """GPU counters (EnumerateCounters / FetchCounters). list_only skips the fetch."""
    params: dict[str, object] = {"list_only": list_only}
    if event_id is not None:
        params["event_id"] = event_id
    if name_filter is not None:
        params["name_filter"] = name_filter
    return bridge.call("get_counters", params)


@mcp.tool
def get_snapshot(event_id: int) -> dict:
    """Compact event snapshot: action + RT ids + bound shader ids. Not a full dump."""
    return bridge.call("get_snapshot", {"event_id": event_id})


@mcp.tool
def list_sections() -> dict:
    """Capture-file sections (VFS-like: names/types/sizes)."""
    return bridge.call("list_sections")


@mcp.tool
def get_section(
    index: int | None = None,
    name: str | None = None,
    max_bytes: int = 4096,
) -> dict:
    """Read one capture-file section (capped base64). Pass index or name.

    Refuses sections whose uncompressed size exceeds 4 MiB — GetSectionContents
    has no prefix-read, so a framecapture section would otherwise load entirely.
    """
    params: dict[str, object] = {"max_bytes": max_bytes}
    if index is not None:
        params["index"] = index
    if name is not None:
        params["name"] = name
    return bridge.call("get_section", params)


@mcp.tool
def write_section(
    name: str,
    contents: str,
    section_type: Literal["unknown", "notes", "bookmarks", "resrenames"] = "unknown",
) -> dict:
    """Write/overwrite a small capture-file section (WriteSection).

    Restricted to notes/bookmarks/resrenames/unknown. FrameCapture and other
    internal sections are rejected. Contents cap 64 KiB. Call save_capture to
    persist a copy of the modified .rdc.
    """
    return bridge.call(
        "write_section",
        {"name": name, "contents": contents, "section_type": section_type},
    )


def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()
