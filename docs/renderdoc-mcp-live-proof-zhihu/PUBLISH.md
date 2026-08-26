# 知乎专栏粘贴说明

知乎不渲染 mermaid，也不显示 SVG。本文配图全部是 PNG，按顺序在编辑器里上传后，再贴正文。

## 标题

逆向 Radiance Cascades：用 RenderDoc MCP 从一帧 .rdc 里读懂一门竞品算法

## 导语

打开一帧竞品全局光照算法的捕获，用 RenderDoc MCP 从 .rdc 里整段取出 shader 源码，追着数据流把它拆成六根枝，逐枝讲清，最后改两行 shader 验证——C0 写红全屏红、去 merge 全屏曝白。

正文结构：标题下 TL;DR → **为什么用 MCP 逆向（正文第一块）** → 错路对照 → 脉络（是什么/不是什么表）→ 树全貌（完整源码）→ 六根枝 → 合并还原 → 改一行验证 → 收获和结论 → PS / PPS / PPPS。

## 配图上传顺序（14 张）

1. `images/01-why.png` — 为什么用 MCP 逆向（验证哪条能力）
2. `images/02-wrong-right.png` — 错路对照（只读源码 vs 源码+捕获对账）
3. `images/03-thread.png` — 脉络（需求→接缝→树根→主干→切开）
4. `images/04-pipeline.png` — 树全貌（6 级级联 + 最终消费）
5. `images/05-main-modes.png` — 枝 1：一个 shader 三种模式
6. `images/06-decode-probe.png` — 枝 2：decodeProbe
7. `images/07-trace-scene.png` — 枝 3：traceScene
8. `images/08-shade-local.png` — 枝 4：shadeLocal（α 量尺）
9. `images/09-merge-upper.png` — 枝 5：mergeUpper（接力）
10. `images/10-feedback-final.png` — 枝 6：feedbackB + final
11. `images/11-reassemble.png` — 合并还原
12. `images/12-ablation-red.png` — 验证一：C0 写红（重放导出）
13. `images/13-ablation-nomerge.png` — 验证二：去 merge（重放导出）
14. `images/14-takeaway.png` — 能抄走的五句

第 12、13 张是改 shader 重放后从 `new_rc_split_frame24.rdc` 真实导出的帧。其余是说明图。正文里的 `![…](images/….png)` 粘贴后不会自动带上本地文件；在对应位置插入刚上传的图即可。

配套交互页面：`rc-visualizer.html`（同目录，浏览器直接打开）——可视化空间密度/角密度/merge，以及每层真实 atlas 的 RGB + 距离 α 视图（可 pan/zoom 看探针块）。

## 标签建议

RenderDoc、GPU 调试、全局光照、Radiance Cascades、MCP
