# 知乎专栏粘贴说明

知乎不渲染 mermaid，也不显示 SVG。本文配图全部是 PNG，按顺序在编辑器里上传后，再贴正文。

## 标题

逆向 Radiance Cascades：先给你完整源码，再跟着我的思路一段段拆

## 导语

这一篇不写说明文。先放完整 shader 源码（26 KB，从 .rdc 里取出的原文），再沿着「追数据流」这条线把它拆成六段，每段配一张图、一个比喻，最后拼回去，改两行 shader 验证理解。

正文结构：标题下 TL;DR → 拆解思路 → 完整源码 → 片段 1–6（入口 / decodeProbe / traceScene / shadeLocal / mergeUpper / feedback）→ 合并还原 → 改两行验证 → 收获和结论 → PS / PPS / PPPS。

## 配图上传顺序（11 张）

1. `images/03-breakdown-logic.png` — 拆解思路（追数据流）
2. `images/05-main-modes.png` — 入口：一个 shader 三种模式
3. `images/06-decode-probe.png` — decodeProbe（查座位表）
4. `images/07-trace-scene.png` — traceScene（手电筒打 13 图元）
5. `images/08-shade-local.png` — shadeLocal（α 是量尺）
6. `images/09-merge-upper.png` — mergeUpper（接力 + 锥形可见性）
7. `images/10-feedback-final.png` — feedbackB（问 C0）
8. `images/11-reassemble.png` — 合并还原流水线
9. `images/14-ablation-red.png` — 验证一：C0 写红（重放导出）
10. `images/15-ablation-nomerge.png` — 验证二：去 merge（重放导出）
11. `images/16-takeaway.png` — 能抄走的五句

第 9、10 张是改 shader 重放后从 `new_rc_split_frame24.rdc` 真实导出的帧。其余是说明图。正文里的 `![…](images/….png)` 粘贴后不会自动带上本地文件；在对应位置插入刚上传的图即可。

## 标签建议

RenderDoc、GPU 调试、全局光照、Radiance Cascades、MCP
