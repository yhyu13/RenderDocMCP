# RenderDoc MCP 竞品研究：人类专家能做、agent 还不能做的（2026-08-29）

## 背景

两个问题：**（1）** 人类专家在 RenderDoc GUI 里对着 .rdc 能做、而 RenderDocMCP 工具面不支持的能力有哪些；**（2）** 单像素调试（single pixel debug）MCP 能不能做、agent 能不能拿到**完整调试轨迹**（all trajectory）。

对标基线不是 RenderDoc 官方 feature list，而是 `renderdoc-skill/renderdoc-human-experience.md`（2026-08-21 调研，Baldur/Matias/Jeremy 一线工作流），它是本仓库自己认的"人类专家 spec"。

**结论先行：**

- **90% 人类循环（Event Browser → Texture Viewer → Pipeline State → Mesh Viewer → Pixel History）MCP 已全覆盖，55 个工具够用。** 差距在长尾：真实剩下的硬缺口是 8 项，其中只有 1 项必须改代码才能解决——就是问题 2 的全轨迹。
- **单像素调试：已经能做。** `pick_pixel` → `get_pixel_history` → `debug_pixel` 三连就是人类"谁写了这个像素"循环的 agent 版。
- **全轨迹导出：现在做不到，但不是因为 RenderDoc 不给，是 MCP 自己丢了。** 扩展侧本来就拿到了整条状态流（≤256 步），只在打包 JSON 时把中间步的变量**值**全部扔掉、只留最后 8–32 步的名字。RenderDoc Python API 的 `ContinueDebug` 循环能走完 1 万–1.5 万步的完整轨迹，人类 GUI 的 Shader 窗口就是走这个循环。修法不是提上限回 JSON（token 炸弹，违反仓库铁律），而是**新增一个导出工具：走完整循环、全量写文件、只返回路径+统计**——与 `export_buffer`/`export_texture` 同一个模式，仓库已有先例。

---

## Q1：差距清单

按"要不要动代码"分三类。工具计数以 `mcp_server/server.py`（954 行，2026-08-29）的 `@mcp.tool` 定义为准，共 55 个。

### A. 已覆盖——人类 90% 循环无需补

| 人类动作 | MCP 工具 | 锚点 |
|---|---|---|
| Event Browser 过滤/跳转（含 Unity 噪音 preset） | `get_draw_calls(marker_filter/exclude/preset)`、`set_event`、`get_snapshot` | server.py:48,589,900 |
| Pipeline State（RS/DS/OM/绑定） | `get_pipeline_state` | server.py:286 |
| 右键取一个像素 | `pick_pixel`（GL 上也是 top-left 原点） | server.py:456 |
| **Pixel History（killer feature）** | `get_pixel_history`（passed/failed.depth/scissor/discard） | server.py:485 |
| Mesh Viewer 输入 vs VS 输出（采样版） | `get_mesh_data(max_vertices=8)` | server.py:517 |
| 资源时间线（usage strip） | `get_resource_usage` | server.py:530 |
| Shader 源码/反汇编/cbuffer | `get_shader_source`、`get_shader_info` | server.py:340,205 |
| 改 shader → 重放 → 验证闭环（比人类 F5 热重载更强） | `compile_shader`→`replace_shader`→`replay_event` + rdc_harness L1/L2 | server.py:360,395,434 |
| 性能：哪一步贵 | `get_action_timings`、`get_counters` | server.py:171,885 |
| 直方图/NaN 检查（数值版 overlay） | `get_texture_stats`（GPU GetMinMax/GetHistogram） | server.py:810 |
| 导出 RT/纹理/buffer/缩略图 | `export_render_target`、`export_texture`、`export_buffer`、`get_thumbnail` | server.py:627,600,657,645 |
| 自定义可视化 shader | `compile_custom_shader`（BuildCustomShader） | server.py:871 |
| 捕获文件管理 | `list/open/save/convert_capture`、sections 读写 | server.py:309-326,911-945 |

### B. 有差距——真实缺口 8 项，按影响排序

| # | 人类专家能力 | MCP 现状 | 差在哪、锚点 |
|---|---|---|---|
| 1 | **Shader 调试窗口逐步看变量值**（每一状态的全部 local 值、watch 面板） | 只回最后 8–32 步的**名字**，值只在终点保留 ≤24 个 | 见 Q2，本文主线 |
| 2 | Texture Viewer **内建 overlay**（Highlight Drawcall / Depth Test 红绿 / NaN-Inf / Quad Overdraw / Triangle Size / Clipping）——专家的第一遍目诊（human-experience.md:33-40） | 无 overlay 等价物；只能 `get_texture_stats` 数值近似或自写 custom shader+导出后看图 | GUI 一眼看的"哪些像素 depth fail 变红"，agent 要全帧扫数值才知道 |
| 3 | Mesh Viewer **全量视图**：滚全部 VB/IB、线框、点任意顶点 | `get_mesh_data` 默认 8 顶点采样 | "200 万三角形哪个退化"类问题需 `export_buffer` 离线算；没有全量网格统计工具 |
| 4 | **API Inspector**（原始 API 调用流+参数，"nothing rendered" 的一环，human-experience.md:65） | 扩展侧无任何 APIInspector/GetAPIEvents 调用（grep renderdoc_extension，2026-08-29 为空） | agent 诊断"啥都没画出来"时缺一条证据链 |
| 5 | **实时触发捕获**（F12 / TriggerCapture / 启动即注入） | 扩展侧 grep TriggerCapture/CaptureFrame 为空；只能 `list_captures`/`open_capture` 开现成 .rdc | 仓库边界上这是 rdc-cli / ue-renderdoc-auto-capture 的活，但严格说是专家有的能力、MCP 没有 |
| 6 | **Statistics 窗口**：按资源排内存 top-N | `get_frame_summary` 只有计数（server.py:95-106）；要手工 `list_resources`+逐个 `get_texture_info` 聚合 | agent 可以拼，但没有一步到位的聚合表 |
| 7 | **锁定 tab 跨事件 A/B 对比**（同纹理 before/after 一眼 diff） | 无 diff 工具；两次 `pick_pixel`/`export` 后外部比 | 人类 UI 免费送的能力，agent 每次都是两次查询+自己算 |
| 8 | GUI 调试器**交互控制**：断点、单步续走、随时停 | 一次性走完即 `FreeTrace`（debug_service.py:51-55），不能"停在 500 步看现场" | 缺口 1 的文件导出方案可等价解决大半（离线切片替代交互停） |

### C. 结构性缺口——补不齐，只能设计上绕

**内嵌 Python 控制台。** 专家在 qrenderdoc 里能对 live replay 跑任意脚本（自定义统计、非常规扫描、驱动任何 ReplayController 方法）。MCP 是固定 55 工具的封闭集合，凡列表外皆不可为。这不是加一个工具能解决的，是封闭工具面 vs 任意脚本的本质差别。两条绕法：按需加工具（现状，B 类就是这么来的），或未来加一个受限的通用 passthrough（安全/token 设计代价大，暂不建议）。`rdc_harness` 的编排库算是半个逃生口，但它也是固定程序。

---

## Q2：单像素调试与全轨迹

### 现状链路：单像素调试已经有了

```text
get_pixel_history(event, x, y)      # 谁写了这个像素，谁 depth-fail（server.py:485）
  → 选最后一个 passed=true 的 fragment   # 人类纪律：调 last passing，不是随便挑
    → debug_pixel(event, x, y)      # 单像素 PS 逐指令走（server.py:675）
    → debug_vertex / debug_thread   # VS / compute 同款（server.py:705,729）
```

三个入口都是 `SetFrameEvent` → `DebugPixel/DebugVertex/DebugThread` → `ContinueDebug` 循环（debug_service.py:34-42），返回 `available/reason` 而不是裸异常。限制：shader 调试仅 D3D11/D3D12/Vulkan；实测 OpenGL 捕获上 `debug_pixel` 因无调试信息不可用（JOURNEY.md 2026-08-23，frame480 实测）。这些和人类 GUI 遇到的是同一堵墙（human-experience.md:115）。

### 三层截断：全轨迹丢在哪（证据）

用途句：下面这段是截断逻辑本体，看 `HARD_MAX_STEPS`、`HARD_LAST_N` 和 `summarize_state` 的返回字段——它证明"中间步的值在扩展侧就被扔了"，不是 IPC 或 MCP 层的锅。

```python
# renderdoc_extension/utils/debug_trace.py:6-9, 56-70
DEFAULT_MAX_STEPS = 64
HARD_MAX_STEPS = 256
DEFAULT_LAST_N = 8
HARD_LAST_N = 32

def summarize_state(st):
    ...
    return {
        "step": getattr(st, "stepIndex", None),
        "next_instruction": getattr(st, "nextInstruction", None),
        "flags": flags,
        "changed": names,   # 只有变量名；before/after 的值在这里被丢弃
    }
```

解释句：全轨迹被砍三层——(1) 循环本身在 256 步封顶（`clamp_max_steps`，debug_trace.py:12-18；循环条件 debug_service.py:34），而真实 PS 轨迹量级是 1 万–1.5 万步（human-experience.md:200）；(2) 走到的 ≤256 个状态里只回最后 ≤32 个（`cap_states`，debug_trace.py:123-127）；(3) 留下的状态只有步号/下一条指令/flags/**变量名**，值只从最后一步捞 ≤24 个（`final_variables`，debug_trace.py:73-88）。另外每次调用结束无条件 `FreeTrace`（debug_service.py:51-55），trace 不可复用，"稍后再问第 500 步"做不到。Pixel History 有自己的截断：默认 32 条、硬上限 128（pixel_service.py:182-185）。

### 方案对比

| 方案 | 做法 | 判定 |
|---|---|---|
| A. 提硬上限（256→∞，32→∞）回 JSON | 改两个常量 | **否**。1.5 万步 × 每步变量 = token 炸弹；违反仓库铁律"never the full ISA dump"（debug_trace.py:3）和 non-goal"Don't dump full bytes into LLM context"（human-experience.md:237） |
| B. 全量状态进 JSON 响应 | 扩 `cap_states` | 同 A，换汤不换药 |
| **C. 全量导出到文件（推荐）** | 新工具 `debug_trace_export(event_id, x, y, ..., path)`：走**完整** `ContinueDebug` 循环（循环体已有，只去掉/放宽 max_steps 停止条件），每步全字段序列化（stepIndex、nextInstruction、flags、changes 的 before/after 名+值），写 JSONL/CSV 到文件，响应只回 `{path, total_steps, truncated:false, anomalies, final_variables}` | agent 拿到路径后用 Read(offset/limit)/grep 任意切片——**全轨迹可得且上下文安全**。模式先例：`export_buffer`/`export_texture`/`get_section` 全是"返回路径/封顶字节"（server.py:657,600,911）。确定性：replay 确定下同一 event+pixel 重走结果一致 |
| D. 分段重走（每次查询重 DebugPixel 走 N 步） | windowed query | C 的劣化版：每问一次付一次完整重走；且中间步值仍需改 `summarize_state` |

### 落地骨架（下一轮 plan 的输入）

> 状态（2026-08-29）：已按本骨架实现 **pixel 入口** `debug_trace_export`（utils/service/facade/handler/server 五层 + DEBUG_METHODS 120s + cache bypass + README 行；170/170 tests）。VS/compute 入口与真机全轨迹实测仍开放。

1. `renderdoc_extension/utils/debug_trace.py`：加 `serialize_state_full`（保留 before/after 值；浮点用 Python 原生 json，`allow_nan=False` 需先清洗 NaN/Inf → 字符串标记）。
2. `renderdoc_extension/services/debug_service.py`：`debug_pixel/vertex/thread` 加 `dump_path` 参数（或独立 export 方法）；导出模式不走 `cap_states`，写文件；`%TEMP%/renderdoc_mcp/` 与 IPC 同目录最顺。Python 3.6 stdlib-only 边界不变。
3. `mcp_server/server.py`：新 `@mcp.tool debug_trace_export(...)` 返回路径+统计，不回字节。
4. 缓存：导出工具 bypass（对齐 cache 规则：export/debug 类不缓存）。
5. 测试：stdlib unittest，duck-type trace 对象（对齐 tests/test_write_tools.py:67-92 风格），GPU-free。
6. 注意写侧教训：`replay_event` 类调用要 120s 超时档（JOURNEY.md 2026-08-22 hang 教训），全轨迹导出耗时更长，应直接挂长超时。

## 风险

- **部分 GPU/API 上 DebugPixel 直接不可用**（GL 无调试信息已实测）；导出循环要处理空 batch 与中途异常，返回 `available:false+reason` 而非半截文件。
- **文件体积**：1.5 万步全量 JSONL 估 MB 量级（具体待实测），一次性成本可接受，但不要把它读进上下文——工具文档必须写明"用 Read 切片"。
- **wave/quad intrinsics 会让整条轨迹不可信**（human-experience.md:115）——导出全轨迹不豁免这条物理限制，文档要标。
- 导出走 replay 线程，`BlockInvoke` 内不要碰 UI 调用（JOURNEY.md 2026-08-22 死锁教训）。

## 数据来源

| 锚点 | 内容 |
|---|---|
| mcp_server/server.py（55 个 `@mcp.tool`，954 行） | 当前工具面全量 |
| renderdoc_extension/utils/debug_trace.py:6-9,56-70,73-88,123-144 | 三层截断证据 |
| renderdoc_extension/services/debug_service.py:34-42,51-55 | 循环与 FreeTrace |
| renderdoc_extension/services/pixel_service.py:172-212 | pixel history 32/128 截断 |
| renderdoc-skill/renderdoc-human-experience.md | 人类专家 spec（90% 工具包、overlay 清单、10k-15k 步、token 纪律） |
| JOURNEY.md（2026-08-22/23） | GL 上 debug_pixel 不可用、replay 死锁教训、写侧边界 |
| grep renderdoc_extension（TriggerCapture/APIInspector/GetAPIEvents，2026-08-29） | 差距 #4/#5 的"没有"证据 |
