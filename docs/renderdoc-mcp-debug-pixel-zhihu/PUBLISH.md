# 知乎专栏粘贴说明

知乎不渲染 mermaid，也不显示 SVG。本文配图全部是 PNG，按顺序在编辑器里上传后，再贴正文。

## 标题

一个像素错了怎么查？我把人类的 GPU 调试杀手链教给了 AI

## 导语

一帧 43.9 MB 的 OpenGL 生产捕获，中心像素颜色可疑。AI agent 用人类图形程序员的三步杀手链——pick_pixel → pixel history → 调最后一个 passing fragment——真机锁定了 12 步着色器轨迹，并且用一个新的全轨迹导出工具拿到了人类 GUI 里都看不全的东西：每一步每个变量的 before/after 值。颜色是哪条指令算出来的、中间被搬运了几次，轨迹里写得明明白白。

正文结构：标题下 TL;DR → 为什么（验证哪条能力，实拍帧）→ 错路对照 → 脉络 → 三层截断 → 树全貌（文件接缝）→ 杀手链真机跑通 → 12 步轨迹数值考古 → 收获和结论 → 讨论口 → PS / PPS / PPPS。

## 配图上传顺序（9 张）

1. `images/final-frame.png` — 为什么/验证哪条（生产捕获最终帧，RenderDoc 真实导出，640×480）
2. `images/03-wrong-right.png` — 错路对照（塞上下文 vs 写文件）
3. `images/04-thread.png` — 脉络（需求→接缝→树根→主干→切开→验证）
4. `images/05-truncation.png` — 三层截断（步数/状态数/值）
5. `images/06-dataflow.png` — 树全貌（DebugPixel→ContinueDebug→状态流→文件）
6. `images/02-killer-chain.png` — 杀手链三步（真数据：320,240 的 pick/history/debug 结果）
7. `images/07-trajectory.png` — 12 步全轨迹时间线（数据来自 trace_e184_320_240.jsonl 实测）
8. `images/atlas-c0.png` — C0 级辐照 atlas（RenderDoc 真实导出，1024×512，颜色的采样来源）
9. `images/08-takeaway.png` — 收获总图（能抄走的六句）

其中第 1、8 张是从 `new_rc_split_frame24.rdc` 真实导出的 GPU 纹理；第 6、7 张按本次会话实跑数据渲染。正文里的 `![…](images/….png)` 粘贴后不会自动带上本地文件；在对应位置插入刚上传的图即可。

## 标签建议

RenderDoc / 图形调试 / GPU / 图形编程 / AI 编程
