# RenderDoc MCP Server

作为 RenderDoc UI 扩展运行的 MCP 服务器。AI 助手可以访问 RenderDoc 的捕获数据，辅助 D3D11/D3D12/**OpenGL** 的图形调试。

> **兼容性说明**: 除 D3D11/D3D12 外，WebGPU（D3D12 后端）的捕获也可作为 D3D12 捕获进行检查。
> 检查工具（`get_shader_info` / `get_buffer_contents` / `get_texture_data`）可直接使用；
> 着色器源码是 Dawn 将 WGSL→HLSL 降级后的 HLSL。OpenGL 捕获走同一套工具（已在 `frame480.rdc` 上实测）。

## 架构

混合进程分离方式：

```
Claude/AI Client (stdio)
        │
        ▼
MCP Server Process (标准 Python + FastMCP 2.0)
        │ 文件 IPC (%TEMP%/renderdoc_mcp/)
        ▼
RenderDoc Process (扩展 + 文件轮询)
```

## 项目结构

```
RenderDocMCP/
├── mcp_server/                        # MCP 服务器
│   ├── server.py                      # FastMCP 入口
│   ├── config.py                      # 配置
│   └── bridge/
│       └── client.py                  # 文件 IPC 客户端
│
├── rdc_harness/                       # 验证 + shader 修复编排核心（纯 Python，无 GPU）
│   ├── models.py                      # 结构化数据模型（CheckResult / VerificationReport 等）
│   ├── rules.py                       # L1 确定性验证 + 自动红线规则引擎
│   ├── behavioral.py                  # L2 行为验证（像素 diff / PSNR / RT 哈希）
│   ├── summarize.py                   # Layer1/Layer2 摘要 + token 压缩
│   ├── orchestrator.py                # shader 编辑 → 重放 → 验证循环
│   ├── renderdoc_backend.py           # 通过 MCP bridge 驱动扩展的适配器
│   ├── report.py                      # before/after 修复报告
│   ├── export.py                      # unified diff + 最终 shader + golden RT 基线
│   └── __main__.py                    # CLI（`python -m rdc_harness frame.json`）
│
├── renderdoc_extension/               # RenderDoc 扩展
│   ├── __init__.py                    # register()/unregister()
│   ├── extension.json                 # 清单
│   ├── socket_server.py               # 文件 IPC 服务器
│   ├── request_handler.py             # 请求处理
│   ├── renderdoc_facade.py            # RenderDoc API 封装
│   └── services/                      # 各领域服务（含 shader_edit_service.py）
│
└── scripts/
    └── install_extension.py           # 扩展安装
```

## MCP 工具

### 数据访问工具

| 工具名 | 说明 |
|---------|------|
| `list_captures` | 获取指定目录内的 .rdc 文件列表 |
| `open_capture` | 打开捕获文件（已有捕获会自动关闭） |
| `get_capture_status` | 确认捕获读取状态 |
| `get_draw_calls` | 绘制调用列表（层级结构、支持过滤） |
| `get_frame_summary` | 帧整体统计（绘制调用数、标记列表等） |
| `find_draws_by_shader` | 按 shader 名称反查绘制调用 |
| `find_draws_by_texture` | 按纹理名称反查绘制调用 |
| `find_draws_by_resource` | 按资源 ID 反查绘制调用 |
| `get_draw_call_details` | 特定绘制调用的详情 |
| `get_action_timings` | 获取 action 的 GPU 执行时间 |
| `get_shader_info` | shader 反汇编 / 常量缓冲区 |
| `get_buffer_contents` | 获取缓冲区数据（可指定 offset/长度） |
| `get_texture_info` | 纹理元数据 |
| `get_texture_data` | 纹理像素数据（支持 mip/slice/3D 切片） |
| `get_pipeline_state` | 完整管线状态（含 rasterizer / depth_stencil / blend） |
| `pick_pixel` | 读取单个像素（Texture Viewer 右键；优先于整张 `get_texture_data`） |
| `get_pixel_history` | 像素历史：谁写入了该像素、谁因 depth/stencil/backface 失败 |
| `get_mesh_data` | Mesh Viewer：采样 VS 输入 vs VS 输出（默认 8 个顶点） |
| `get_resource_usage` | 资源在帧内的读写事件（时间线 usage strip） |

### 会话 / 导出（Phase 1）

| 工具名 | 说明 |
|---------|------|
| `close_capture` | 关闭当前捕获 |
| `save_capture` | 把带 shader/resource 替换的捕获另存为新 `.rdc` |
| `embed_dependencies` / `remove_dependencies` | 把 shader debug 文件嵌入/移出捕获（`debug_*` 可移植） |
| `list_capture_formats` / `convert_capture` | 列出可转换格式并导出捕获 |
| `set_event` | 把 UI（Texture Viewer 等）跳到指定 event（`SetEventID`，不是纯 replay） |
| `export_texture` | `SaveTexture` 到磁盘；JSON 只返回路径，不塞图 |
| `export_render_target` | 导出该 event 的 color target |
| `get_thumbnail` | 最后一次 present/draw 的 color target 缩略图 |
| `export_buffer` | 把 buffer 字节写到文件 |

### Shader 步进调试（Phase 2）

| 工具名 | 说明 |
|---------|------|
| `debug_pixel` | 像素着色器步进（默认 64 步 / 最后 8 态，硬顶 256；bridge 超时 120s） |
| `debug_vertex` | 顶点着色器步进 |
| `debug_thread` | Compute 单线程步进 |
| `debug_trace_export` | **全轨迹导出**：走完整个 `ContinueDebug` 循环，逐步（含变量 before/after 值）写 JSONL 文件，只回路径+统计（默认 `%TEMP%/renderdoc_mcp/exports/trace_e*.jsonl`）；用 Read/grep 切片，勿整读。真实 PS 轨迹 1 万–1.5 万步；120s 超时档；缓存 bypass |

### 资源目录 + 通用替换（Phase 3）

| 工具名 | 说明 |
|---------|------|
| `list_resources` / `get_resource` | 资源目录与元数据（含是否已被替换） |
| `replace_resource` | 通用 `ReplaceResource` + `RegisterReplacement`（纹理/缓冲/shader；可 `save_capture` 持久化。不能写入纹理/缓冲字节，只能换 ResourceId） |
| `restore_resource` / `restore_all_replacements` | 撤销替换 |
| `get_texture_stats` | GPU `GetMinMax` 每通道 min/max + 可选 16-bucket histogram；**不**把整张图读进 Python |

### Shader 扩展（Phase 4）

| 工具名 | 说明 |
|---------|------|
| `list_shader_encodings` | 该捕获 API 支持的 target / custom 编码 |
| `list_shaders` / `shader_map` | 帧内 shader 列表与 event×stage 映射 |
| `search_shaders` | 在反汇编中搜子串（短 snippet，不是整份 ISA） |
| `compile_custom_shader` | `BuildCustomShader`（可视化 shader，不是 target 替换；OpenGL GLSL `<420` 且含 `layout binding` 时自动升到 `#version 420`） |

### 计数器 / 快照 / 捕获节（Phase 5）

| 工具名 | 说明 |
|---------|------|
| `get_counters` | GPU counters；`list_only` 只枚举不 fetch |
| `get_snapshot` | 紧凑 event 快照（action + RT + shader ids） |
| `list_sections` / `get_section` | 捕获文件节（VFS 式；`get_section` 拒绝 >4 MiB 的节，避免整段 framecapture 进内存） |
| `write_section` | `WriteSection`：写入 notes/bookmarks/resrenames/unknown（内容 cap 64 KiB） |

不在本仓库扩展范围内：live capture / inject / daemon（扩展无法驱动目标进程）；双捕获 diff 与 CI assert 留在 `rdc_harness`。

### Shader 编辑 / 重放工具（rdc 内闭环）

| 工具名 | 说明 |
|---------|------|
| `get_shader_source` | 获取 shader 的原始字节与编码（`is_source_text` 标记是否可编辑） |
| `compile_shader` | 编译 HLSL/GLSL 源为捕获 API 可用的替换 shader。`compile_flags="debug"` 带 `D3DCOMPILE_DEBUG`+`SKIP_OPTIMIZATION`（`debug_pixel` 需要） |
| `replace_shader` | 用编译后的 shader 替换指定 event/stage 的 shader |
| `remove_shader_replacement` | 撤销替换，恢复原 shader |
| `replay_event` | 重放捕获到指定 event（应用所有替换） |
| `get_debug_messages` | 获取验证层诊断消息（L1 确定性验证） |

### get_draw_calls 过滤选项

```python
get_draw_calls(
    include_children=True,      # 包含子 action
    marker_filter="Camera.Render",  # 仅取该标记之下
    exclude_markers=["GUI.Repaint", "UIR.DrawChain"],  # 排除的标记
    event_id_min=7372,          # event_id 范围起点
    event_id_max=7600,          # event_id 范围终点
    only_actions=True,          # 排除标记（仅绘制调用）
    flags_filter=["Drawcall", "Dispatch"],  # 仅保留指定 flag
    preset="unity_game_rendering",  # Unity Editor：Camera.Render + 去掉 GUI/EditorLoop
)
```

人类 90% 工具箱（Event Browser / Texture Viewer / Pipeline / Mesh Viewer / Pixel History）见本仓库 `renderdoc-human-experience.md`（与 sibling `renderdoc-skill/` 同步）。视觉问题优先 `pick_pixel` / `get_pixel_history`，网格问题优先 `get_mesh_data`，不要一上来 `get_texture_data` 整图。

### 捕获管理工具

```python
list_captures(directory="D:\\captures")
# → {"count": 3, "captures": [{"filename": "game.rdc", "path": "...", "size_bytes": 12345, "modified_time": "..."}, ...]}

open_capture(capture_path="D:\\captures\\game.rdc")
# → {"success": true, "filename": "game.rdc", "api": "D3D11"}

close_capture()
save_capture(capture_path="D:\\captures\\game_patched.rdc")
set_event(event_id=7538)
export_texture(resource_id="ResourceId::22573", path="D:\\out\\rt.png")
```

### 反查搜索工具

```python
find_draws_by_shader(shader_name="Toon", stage="pixel")
find_draws_by_texture(texture_name="CharacterSkin")
find_draws_by_resource(resource_id="ResourceId::12345")
```

### GPU 计时获取

```python
get_action_timings()
get_action_timings(event_ids=[100, 200, 300])
get_action_timings(marker_filter="Camera.Render", exclude_markers=["GUI.Repaint"])
```

**注意**：GPU 计时计数器在部分硬件/驱动上不可用。若返回 `available: false`，则该捕获无法获取计时信息。

## Shader 编辑 + 重放闭环

`rdc_harness` 实现了 `.rdc` 内部的「改 → 编译 → 重放 → 验证」闭环（对应感知 Agent 设计文档的 L1/L2 双层验证）：

```
编译 → 静态检查 → 替换 shader → 重放 → L1 确定性验证
  → (失败 ⇒ needs_rebuild) → L2 行为验证 → (分数 ≤ 阈值 ⇒ ok) → 修补 → 重复
```

- **L1 确定性验证**（`rules.py`）：零模型成本，纯规则 —— 帧预算、瓶颈、draw call 数量、pass 耗时、overdraw、带宽、合批、纹理、SetPass/RT 切换、资源绑定完整性、验证层消息（`get_debug_messages`）。
- **L2 行为验证**（`behavioral.py`）：像素 diff、PSNR、渲染目标哈希，与 golden 图对比。
- **编排器**（`orchestrator.iterate_shader_fix`）：`compile → inject → replay → L1 → L2 → patch → repeat` 循环，通过 `ShaderBackend`/`ShaderPatcher` 协议与 RenderDoc 解耦，可无 GPU 单元测试。
- **报告**（`report.py`）：输出 before/after 对比报告，供人工/CI 决策。
- **闭环导出**（`export.py`）：`write_shader_patch` 写出 unified diff + 最终 `.hlsl`；`write_golden` / `check_against_golden` 管理 L2 渲染目标基线（hash sidecar）。

`RenderDocShaderBackend`（`rdc_harness/renderdoc_backend.py`）通过 MCP bridge 调用上述 shader 编辑工具，实现真正的 RenderDoc 侧 I/O：

| 后端方法 | 映射的 RenderDoc API / MCP 工具 |
|---|---|
| `compile_shader` | `BuildTargetShader(entry, enc, source, flags, stage)` |
| `inject_shader` | `ReplaceResource(original, compiled)` |
| `replay` | `SetFrameEvent(eventId, force=True)` |
| `run_l1` | `get_frame_summary` + `get_pipeline_state` + `get_debug_messages` |
| `run_l2` | `get_texture_data` vs golden 字节 |

## 通信协议

文件 IPC：

- IPC 目录：`%TEMP%/renderdoc_mcp/`
- `request.json`：请求（MCP 服务器 → RenderDoc）
- `response.json`：响应（RenderDoc → MCP 服务器）
- `lock`：写入中锁文件
- 轮询间隔：100ms（RenderDoc 侧）

## 开发笔记

- RenderDoc 内置 Python 无 socket/QtNetwork 模块，故采用文件 IPC
- RenderDoc 扩展仅使用 Python 3.6 标准库
- ReplayController 访问通过 `BlockInvoke` 完成
- `rdc_harness` 运行于 AI/MCP 侧（Python ≥ 3.10），**不可**在 `renderdoc_extension/` 内导入（其内置 Python 3.6 无法解析现代注解）
- **不要伪造 `ResourceId`**。C++ `ResourceId.id` 是 private；`rd.ResourceId(); rid.id = n` 得到的是 `ResourceId::0`（Null）。解析必须对照 `GetTextures` / `GetBuffers` / `GetResources` 的**活对象**，`compile_shader` 返回的 id 缓存在本进程里再交给 `replace_shader`。
- **`GetCaptureFile` 在 `ReplayManager` 上**（`ctx.Replay().GetCaptureAccess()`），不在 `CaptureContext`。MCP `LoadCapture` 后 `ctx.GetCaptureFile()` 会是 `None`。节/格式/转换走 `pick_capture_access()`；`embed_dependencies` 优先 `ctx.EmbedDependentFiles()`。
- 改完 `renderdoc_extension/` 必须 `python scripts/install_extension.py` 并**重启 RenderDoc**，否则测的还是旧拷贝。
- `RegisterReplacement` / `UnregisterReplacement` 必须在 `BlockInvoke` **之外**调用（UI 线程）。放进 replay callback 会让下一次 `SetFrameEvent(force=True)` 死锁。
- `replay_event` / `replace_shader` / `compile_shader` / `pick_pixel` 走 120s IPC 超时。OpenGL `frame480` 上带真实替换的 `replay_event(550)` 已实测返回 `{replayed:true}`；若将来再卡住，`pick_pixel` 自己会 `SetFrameEvent(force=True)`。

## 响应缓存（OpenViking 可选后端）

MCP 侧 `mcp_server/cache.py` 在 bridge 外包了一层读穿透缓存。确定性只读工具（`get_pipeline_state`、`get_texture_data`、`get_frame_summary`、`list_resources` 等）命中后不再走文件 IPC 和 GPU 重放；会改变捕获状态或资源的工具（`replace_shader`、`write_section`、`open_capture` 等）绕过缓存并清空缓存；`get_debug_messages` 这类会排空队列、以及导出/单步调试类工具永不缓存。

缓存键 = 捕获身份 + 方法 + 规范化参数。捕获身份来自 `get_capture_status().filename` 并叠加文件 stat（路径、mtime、大小），避免不同捕获里相同 `event_id`/`ResourceId` 互相串数据。

环境变量：

- `RENDERDOC_MCP_CACHE=0`：关闭缓存。
- `RENDERDOC_MCP_CACHE_BACKEND=memory|openviking`：默认 `memory`。`openviking` 需要可导入的 `openviking_sdk`，把条目持久化到 `viking://resources/renderdoc-mcp-cache/<key>.json`（写入用 `processing_mode="vectors_only"`，读回用 `read_raw`）。SDK 不可用时自动回退内存。
- `RENDERDOC_MCP_CACHE_MAX_ENTRY_BYTES`：单条缓存字节上限，默认 4 MiB，超过则不缓存。

设计文档（含自评审）见 `docs/openviking-cache-design.md`。缓存只存在于 MCP 侧（Python ≥ 3.10），**不**进入 `renderdoc_extension/`（Python 3.6 边界）。

## 已知坑（OpenGL `frame480` 实测）

- `compile_shader` → `replace_shader` 必须用**同一次会话**返回的 `resource_id`；不要手拼 `ResourceId::N`。
- `find_draws_by_resource` 禁止用 Null 对 Null（未绑定的 Hull/Domain 都是 `ResourceId::0`）。
- `get_shader_info` 常量缓冲走 `PipeState.GetConstantBlock`（不是 `GetConstantBuffer`）。
- `list_shader_encodings` / mesh `attributes[].format` 用枚举 `.name` / `ResourceFormat.Name()`，不要 `str(swig_ptr)`。
- `Descriptor.numMips` 在部分 API 上是垃圾值（曾出现 233）；超过 1–32 时回退到纹理 `mips`。
- OpenGL 捕获上 `debug_pixel` 通常 `available: false`（无 debug info / API 不支持）；`compile_flags="debug"` 是 D3DCOMPILE_*，不会给 GLSL 造调试符号。
- 实测记录：`live-tool-validation-frame480.md`（产品闭环 + ResourceId/GetCaptureFile 复测）。

## 测试

```bash
# stdlib unittest，无需 pytest
python -m unittest discover -s tests
```

## 参考链接

- [FastMCP](https://github.com/jlowin/fastmcp)
- [RenderDoc Python API](https://renderdoc.org/docs/python_api/index.html)
- [RenderDoc Extension Registration](https://renderdoc.org/docs/how/how_python_extension.html)
