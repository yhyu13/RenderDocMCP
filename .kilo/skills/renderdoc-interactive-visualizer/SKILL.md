---
name: renderdoc-interactive-visualizer
description: Build a single-file interactive HTML page that visualizes a GPU algorithm reverse-engineered from a RenderDoc .rdc capture — real captured data (atlas textures, buffer bytes, shader source) alongside the algorithm's concepts (spatial/angular density, data flow, pipeline steps), with pan/zoom and step-through controls. Use when the user wants to visualize, teach, or make an interactive demo of an algorithm pulled out of a capture.
---

# RenderDoc Interactive Visualizer

## When to use

- The user wants to "visualize" / "make an interactive page" / "teach" a GPU algorithm that is being (or has been) reverse-engineered from a `.rdc` capture.
- Real capture data exists (atlases, buffers, shader source) and should be shown next to the algorithm's concepts.
- Static PNG diagrams are too flat; the reader should drag, zoom, and step through.

## When NOT to use

- No capture is loaded and no real data exists — never fabricate the data.
- A single static diagram is enough.
- The task is a game/demo, not a teaching visualization.

## The two halves

Every algorithm visualization has two halves, and they must stay visually separated and clearly labeled:

1. **Concept half** — the algorithm's *design*: spatial density, angular density, data flow, pipeline steps. Drawn from first principles, animated.
2. **Real-data half** — the algorithm's *actual output*: atlas textures, buffer bytes, shader source. Exported from the `.rdc`, never hand-drawn.

A reader who sees only one half gets confused; a page that mixes them without labels lies. Label every real-data view with provenance (which `.rdc`, which `resource_id`).

## Workflow

1. **Extract real data** (the ground truth):
   - `get_shader_source(event_id, stage)` → source text; `is_source_text` tells GLSL vs binary.
   - `get_buffer_contents(resource_id)` → raw bytes; decode the struct against the shader's SSBO layout.
   - `export_texture(resource_id, dest_type="png")` → atlas / RT as PNG.
   - `get_texture_stats(resource_id)` → per-channel min/max — the numbers that prove the concept.
   - `get_pipeline_state(event_id)` → bindings (shader / SRV / UAV / CB).

2. **Process the data** (Python/PIL):
   - Keep full-res unless the probe grid stops resolving; don't downscale blindly.
   - Extract the α (distance) channel to a colormap — it is often the *trace result* and more informative than RGB.
   - Brighten RGB (radiance is tiny in linear space); label the stretch.

3. **Build the concept half** (canvas, animated):
   - A 2D scene (light + occluder + probe grid + rays) whose parameters are the algorithm's *exact* parameters (probe spacing, ray count, ray length).
   - A slider that changes the parameter and shows the trade-off live.

4. **Build the real-data half**:
   - The atlas image + a probe-grid overlay (each probe = a `probeSize×probeSize` block).
   - A pan/zoom viewer so the reader can inspect any probe.

5. **Add step-through** ("what does this step do"):
   - N buttons = the pipeline stages; each shows a code snippet + input/output + one metaphor.

## Reusable patterns

### Pan/zoom atlas viewer

```js
const zoom = { sx: 448, sy: 224, w: 128, h: 64 };   // source texel coords
const clamp = (v,lo,hi) => Math.max(lo, Math.min(hi, v));
function recenter(clientX, clientY){
  const r = canvas.getBoundingClientRect();
  zoom.sx = clamp((clientX-r.left)/r.width  * SRC_W - zoom.w/2, 0, SRC_W - zoom.w);
  zoom.sy = clamp((clientY-r.top) /r.height * SRC_H - zoom.h/2, 0, SRC_H - zoom.h);
  draw();
}
canvas.addEventListener('mousedown', e => { dragging = true;  recenter(e.clientX, e.clientY); });
canvas.addEventListener('mousemove', e => { if (dragging) recenter(e.clientX, e.clientY); });
window.addEventListener('mouseup', () => dragging = false);
canvas.addEventListener('wheel', e => {            // zoom, keep center
  e.preventDefault();
  const f = e.deltaY < 0 ? 0.75 : 1.33;
  const nw = clamp(zoom.w * f, MIN_W, SRC_W);
  const nh = clamp(zoom.h * f, MIN_H, SRC_H);
  zoom.sx = clamp(zoom.sx - (nw - zoom.w)/2, 0, SRC_W - nw);
  zoom.sy = clamp(zoom.sy - (nh - zoom.h)/2, 0, SRC_H - nh);
  zoom.w = nw; zoom.h = nh; draw();
}, { passive:false });
// draw: main canvas = full image + a red rect at the zoom region;
//       zoom canvas = drawImage(img, zoom.sx, zoom.sy, zoom.w, zoom.h, 0, 0, W, H)
```

### Probe-grid overlay (data-aligned)

Grid spacing in display px = `probeSize * displayWidth / sourceWidth`. Derive it from the algorithm's `probeSize`; never hardcode.

### Readout that proves the concept

Every view shows the numbers (probe count, ray count, min/max) so the reader verifies the trade-off against the source. If the numbers disagree with the source, fix the visualization, not the numbers.

## Data-alignment rule

The visualization's parameters must be the algorithm's actual parameters:

- `probeSize = 2^(cascade+1)`
- spatial density = `grid / probeSize`
- angular density = `rays per probe`
- ray interval = `probeSize * 8 * texelScale`

If you cannot state these from the source, you do not understand the algorithm yet — go back to the capture.

## Deliverable

- `visualizer.html` — single file (inline CSS/JS), zero build, zero CDN.
- `images/atlas/*.png` — the real exported data (RGB + α colormap per cascade).
- Open in a browser and verify: no JS console errors, slider/pan/zoom respond, readout numbers match the source.

## Verify before shipping

- `console` has no errors (a 404 favicon is fine).
- Drive the interactions (Playwright or similar): set the slider, click the canvas, read the readout text.
- Confirm every real-data image has provenance (which `.rdc`, which `resource_id`).

## Worked example

`docs/renderdoc-mcp-live-proof-zhihu/rc-visualizer.html` — Radiance Cascades, four sections:

1. spatial vs angular density (interactive 2D scene, cascade slider).
2. 5-step pipeline stepper (decodeProbe → traceScene → shadeLocal → mergeUpper → imageStore).
3. penumbra-hypothesis table (per-cascade numbers).
4. real atlas per cascade (RGB + α colormap + pan/zoom probe inspector).
