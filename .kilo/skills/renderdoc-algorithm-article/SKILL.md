---
name: renderdoc-algorithm-article
description: Write a deep-dive teaching article that reverse-engineers a GPU algorithm from a RenderDoc .rdc capture and explains it to an audience — grounded in real captured evidence (shader source, buffer decode, atlas hierarchies, shader-edit ablations), following a fixed skeleton (TL;DR → why → wrong/right → thread → tree → branches → takeaways). Use when the user wants to "write an article / explain / teach / dump the learning from reverse-engineering" a GPU algorithm.
---

# RenderDoc Algorithm Article

## When to use

- The user wants an article that reverse-engineers a GPU algorithm from a `.rdc` and teaches it to readers.
- The user says "写文章 / 讲清这个算法 / 把学习沉淀下来 / 给读者讲".
- You have (or can produce) real capture evidence: shader source, buffers, textures, replays.

## When NOT to use

- No capture, no real data — never fabricate the evidence.
- The deliverable is a Zhihu paste pack (use the writing skill for platform rules), not the method itself.

## The skeleton (fixed order)

```
标题
  → TL;DR              3–5 条可抄判断，扫完能走
  → 为什么 / 验证哪条   正文第一块：这篇验证的是什么能力（不是待办说明）
  → 错路对照           先画读者会想错的，再画正路；开口主线落这
  → 脉络               需求 → 接缝 → 树根 → 主干 → 切开（配是什么/不是什么表）
  → 树全貌             整条管线 + 完整源码（源码从 .rdc 取，不是 repo 抄）
  → 按枝往下讲          每个函数 = 一根枝
  → 收获和结论          5–7 条能搬走的判断 + 一句把主线落地
  → PS / PPS / PPPS     三层附言，缺一不可
```

Each branch (枝) is a fixed four-step beat:

```
人话（一句） → 是什么/不是什么 → 代码片段 → 一张图 + caption
```

## Evidence: what to pull from the .rdc, and where it goes

| Evidence | Tool | Goes in |
|---|---|---|
| 完整 shader 源码 | `get_shader_source`（`is_source_text` 判 GLSL vs binary） | 树全貌 |
| 管线结构 / dispatch 数 | `get_frame_summary` | 树全貌（13≠6 这类「文档没写的真相」） |
| buffer 解码（场景契约等） | `export_buffer` → 按 SSBO struct 解码 | 树全貌 / 对应枝 |
| atlas 层级（trace α / 辐照 RGB） | `export_texture` + α 通道 colormap | 对应枝（shadeLocal / merge） |
| 每通道极值对账 | `get_texture_stats` | 对应枝（数字对上源码） |
| 改 shader 重放（merge 开/关等） | `compile_shader` → `replace_shader` → `replay_event` → `export_render_target` | 对应枝（「不这样会怎样」） |

## Figure design rules

1. **每张图都要 caption**：`图 N：一句话`，放在图下方。Caption 是论点的人话版，不是「如图所示」。
2. **颜色语义一致**，不要随手换：
   - 结构/流程 = indigo/蓝
   - 是什么 / 正路 = 绿
   - 不是什么 / 错路 = 红（红字钉「不是什么」）
   - 背景/上下文 = 灰
   - 结论/落锤 = 深 slate（白字，一张图最多一处）
3. **概念图与真实数据图分开**：概念图是画的（管线、数据流），真实数据图是导出的（atlas、buffer、重放帧）。真实数据图必须标来源（哪个 `.rdc`、哪个 resource）。
4. **标题即论点**：图的标题（alt）就是这张图要证明的那句话。

## 写作纪律

- **说人话**：先比喻后术语。α = 量尺，merge = 接力赛，decodeProbe = 查座位，traceScene = 手电筒，probeSize = 半影假设的两条腿。
- **是什么 / 不是什么**：每段先说它是什么，紧跟它不是什么。
- **图先行**：每个独立论点一张图，宁多不少。
- **禁 mermaid / SVG**（知乎不渲染）；图必须是 PNG。
- 去 AI 味：`不是X而是Y` ≤ 2、无黑话（落地/链路/闭环）、意义通胀清零、`真正/确实/实际上` 压到近零。

## 已知坑（写文章时踩过的）

- **`export_texture` / `get_texture_stats` 读的是初始捕获态，不是重放态**。改 shader 重放后想拿「新 atlas」会拿到旧内容；只有 `export_render_target` 反映重放结果。所以「merge 开/关」的对比用最终帧，不用 atlas。
- **`uMode=0`（布局）生产路径从不 dispatch**：布局在 CPU 侧用 oracle 算好，GPU 只跑 transport + final。写「一个 shader 三种模式」时要说清这一点，别让读者以为三路都跑。
- **dispatch 数可能 ≠ 文档写的数**（split-dispatch 没写进注释）。这是「源码 vs 捕获对账」最有说服力的一例。

## Worked example

`docs/renderdoc-mcp-live-proof-zhihu/` — 逆向 Radiance Cascades：
- `article.md`：完整骨架（TL;DR → 为什么 → 错路 → 脉络 → 树 → 六枝 → 收获 → PS/PPS/PPPS）。
- `rc-visualizer.html`：配套交互页（见 `renderdoc-interactive-visualizer` skill）。
- 18 张图：概念图（01–11、14）+ 真实数据图（scene-data / trace-hierarchy / rgb-hierarchy / merge-on-off / final-frame / ablation 帧）。

## Deliverable

- `article.md`（无 mermaid/SVG，每图有 caption）
- `images/*.png`（概念图 + 真实数据图）
- `PUBLISH.md`（标题、导语、上传顺序）
