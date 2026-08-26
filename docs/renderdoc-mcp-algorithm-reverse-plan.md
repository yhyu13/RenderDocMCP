# 大纲 + 执行 plan：用 RenderDoc MCP 逆向并讲清一门竞品算法

> 定位：不是「证明 MCP 能导出一个 buffer」，是「证明 MCP 能像人类专家一样，把一门竞品全局光照算法从一帧捕获里整条扒出来、读懂、再教给别人」。从标题到最后一个字、每一张图都重写。

## 〇、竞品研究（Radiance Cascades）

### 身份与出处

- **算法**：Radiance Cascades（辐射级联），实时全局光照（GI）。
- **作者**：Alexander Sannikov，Grinding Gear Games（Path of Exile）图形程序员。
- **原始论文（WIP/preprint）**：*Radiance Cascades: A Novel Approach to Calculating Global Illumination*（radiance.wiki/papers/sannikov-original）。
- **学术扩展**：Osborne & Sannikov 2024，把 RC 用到多维非 LTE 天体物理辐射传输（*RAS Techniques and Instruments*, 2024-12-19, arXiv:2408.14425）——证明这套东西离开游戏渲染也成立。
- **社区资料**：radiance.wiki、radiance-cascades.com、GM Shaders 教程（Yaazarai/Alex）、SimonDev、Jason McGhee、mxcop 的 fundamentals。
- **逆向对象**：`new_rc_split_frame24.rdc`（OpenGL，43.9 MB，phase12_d split-dispatch 版）。源码在 `D:\GitRepo-My\radiance-cascades-demo\3d\`，已通读 shader / pipeline / layout。

### 核心机制（为什么这么设计）

1. **半影假设（penumbra hypothesis）**：阴影的半影，靠近光源要「线性（空间）分辨率」高，远离光源要「角分辨率」高，两者成反比。这是整个算法的出发点——也是文章要教给读者的第一个概念。
2. **级联（cascade）**：每级是一张探针网格。C0 最密（空间分辨率最高）但每探针射线最少（角分辨率最低）；每上一级，探针数 ÷4（每轴 ÷2），射线数 ×4（每轴 ×2）。源码里就是 `probeSize = 2^(cascade+1)`：C0=2（4 方向）→ C5=64。
3. **探针（probe）**：一组共享射线原点的 texel，每个 texel 存一个方向的辐照。
4. **合并（merge）**：自顶向下（最粗 N → C0），每级读上一级的 4 个双线性探针插值合并。这就是「用有限射线模拟无限方向」的来源——RC 最有记忆点的一句。
5. **可见性项（α 通道）**：文献里是 0/1（打没打中）；这套实现存的是「首击距离」——打中 = h.t，没打中 = −1.0，merge 里用它做遮挡判断。**捕获里 α min = −1.0 就是从这里来的。**

### 竞品概念 ↔ 源码 ↔ 捕获数据（三线对账，这是全文的骨架）

| 竞品概念 | 源码出处 | 捕获证据 |
|---|---|---|
| probeSize = 2^(cascade+1) | `reference_layout.h:16-27` | C0 亮近 / C5 暗远（stats） |
| α = 距离，miss = −1.0 | `reference_transport.comp:359` | α min = −1.0（get_texture_stats） |
| merge 自顶向下，4 双线性探针 | `mergeUpper`（cascade<5） | 每级 `uUpperCascade` 指向上级 atlas |
| final 消费 C0 画到屏上 | `shadeFinalView` | 最终帧间接光 |

## 一、目标（4 条）

1. **验证 MCP 能力**——及格线不是「能导出」，是「能拿出整条管线」。
2. **拿出整个管线**——C5→C0 六级级联 + 最终消费，一次 dispatch 不漏，数据怎么流、每级绑什么全摆出来。
3. **像人类专家一样分析算法**——讲清「为什么」（半影假设）、「怎么拆」（级联/探针/合并/可见性），不是罗列 13 次 dispatch。
4. **教会别人这个竞品算法**——读者读完能自己讲清 Radiance Cascades，能自己跑 MCP 复现逆向。

## 二、对「竞品算法」的定位（已确认）

- 竞品算法 = **Radiance Cascades**（Sannikov 的实时 GI 技术），App3D 里 `reference_transport.comp` 是它的语义内核。
- 读者默认不认识这个算法；文章把它教到「能讲清 + 能复现」。

## 三、大纲（从标题开始）

### 标题

**逆向 Radiance Cascades：用 RenderDoc MCP 从一帧 .rdc 读出整条竞品算法**

### 骨架

```
TL;DR（5 条可抄走）
  → 为什么用 MCP 逆向（验证哪条能力，正文第一块，配图）
  → 对象：Radiance Cascades 是什么（半影假设 + 级联/探针/合并，配图）
  → 五步调用（打开 → 帧结构 → 绑定 → 导出 → 对账，配图 + 是什么/不是什么表）
  → 管线全貌（6 级级联 + 最终消费，13 dispatch 的来源，配图）
  → 算法拆解（核心，配图 ×3）
        · 一个 shader 三种模式（uMode 0/1/2）
        · transport：decodeProbe → traceScene → shadeLocal（α=距离在这落笔）
        · merge：自顶向下、4 双线性探针、按距离融合（"有限射线模拟无限方向"）
        · feedback：只回读 C0；final：消费 C0 画到屏上
  → 数字对账（α min = −1.0 对上源码第 359 行；C0 亮近 C5 暗远 = 半影假设）
  → 教给读者（三句话讲清算法 + 复现步骤）
  → 收获和结论（5–7 条 + 一段）+ PS / PPS / PPPS
```

### 每节「讲什么 / 证明什么 / 配什么图」

| 节 | 讲什么 | 证明什么 | 图 |
|---|---|---|---|
| TL;DR | 5 条判断 | 扫完能走 | — |
| 为什么逆向 | 逆向不是「能导出」，是「能读懂」 | 三条能力压到一次逆向 | 探针图（重画） |
| 对象 | 半影假设 → 级联/探针/合并 | 读者建立整体认知 | 算法概念图（重画） |
| 五步调用 | 打开→帧结构→绑定→导出→对账 | MCP 操作路径 | 流程图（重画） |
| 管线全貌 | C5→C0 + final，13 dispatch 怎么来 | 「拿出整个管线」 | 管线图（重画） |
| 算法拆解 | 一个 shader 三种模式；transport/merge/feedback/final | 「像专家分析」 | 数据流图 ×3（新画） |
| 数字对账 | α min=−1.0 对上源码；C0 亮 C5 暗 = 半影假设 | 读出的数字 = 源码语义 | 真实 atlas（已有 01–03） |
| 教给读者 | 三句话 + 复现步骤 | 「教会别人」 | 收获图（重画） |

## 四、执行 plan

### Phase 0 — 读源码（已完成大半）

- [x] `reference_transport.comp`（traceScene / shadeLocal / mergeUpper / feedbackB / decodeProbe / main 三模式）。
- [x] `reference_pipeline.cpp`（**已确认 13 = 6×2 + 1**：每级两次 `glDispatchCompute`，主区 (0,0) + 内部区 (0,256)）。
- [x] `reference_layout.h`（probeSize = 2^(cascade+1)、texelScale 1/256、bandHeight 256、C5 reach 10000）。
- [ ] `reference_rc_atlases.cpp`——atlas 格式/过滤坐实。
- [ ] `reference_cornell_scene.cpp`——13 个 primitive 是什么（墙/灯/箱/圆柱/镜面球/排除算子）。

### Phase 1 — 用 MCP 扒整条管线

- [x] `get_capture_status`、`get_frame_summary`、`get_draw_calls(flags_filter=Dispatch)`、`list_shaders`。
- [ ] `get_pipeline_state` 打满 6 个 cascade 的首 dispatch（20=C5、43=C4、66=C3、89=C2、112=C1、135=C0）——坐实 `uUpperCascade` 逐级指向上级。
- [ ] `get_shader_info(event, compute)` 每级一次——读出 `$Globals` 的**值**（`uCascade`/`uPhysicalWidth`/`uEnableUpperMerge` 逐级怎么变）。
- 验证：一张「6 级 × 绑定」对照表，和 `reference_pipeline.cpp:61-99` 逐行对上。

### Phase 2 — 导出证据

- [x] 最终帧、C0/C5 atlas、Buffer 59 hex、C0/C5 stats。
- [ ] 补 C1（或 C3）atlas + stats——「细/中/粗」三档梯度。
- [ ] `get_buffer_contents` 场景 SSBO（`SceneData`）坐实 `primitives[13]`。
- 验证：三档 atlas 的 RGB max / α max 呈单调梯度（C0 > C1 > C5）。

### Phase 3 — 写正文 + 重画全部说明图

- 正文：标题 → 最后一个字，按第三节大纲写，边写边过 content-craft 去 AI 味（`不是 X 而是 Y` ≤ 2、无黑话、术语首现落地、中英文空格、直角引号）。
- 图：说明图全部重画（6 张左右），标题即论点、红字钉「不是什么」；真实导出图 01–03 保留，补 C1/C3 后多 1–2 张。
- 核心新图：「算法拆解数据流」图——一条从 `traceScene` 打到 `imageStore(uBandImage)` 的线，标注 α=−1.0 落笔处。

### Phase 4 — 质检 + 交付

- content-craft 质检扫描（滑回 / 意义通胀 / 源头保真 / 单一论点 / 活人感）。
- 抽读三段：是否有具体对象（6 cascade、13 primitive、α=−1.0）、具体动作、具体判断。
- 更新 `PUBLISH.md`。

## 五、还缺的证据

| 缺什么 | 怎么补 | 用在哪 |
|---|---|---|
| 6 级各自的 pipeline state | `get_pipeline_state` × 6 | 管线全貌 / 每级绑什么 |
| 6 级 `$Globals` 常量值 | `get_shader_info` × 6 | 证明逐级参数怎么变 |
| C1 或 C3 的 atlas + stats | `export_texture` + `get_texture_stats` | 级联梯度三档对比 |
| 13 个 primitive 是什么 | 读 `reference_cornell_scene.cpp` | traceScene 教学 |

## 六、风险 / 待确认

1. **竞品定位已确认** = Radiance Cascades（Sannikov）。文献里 α 是 0/1 可见性，这套实现存「距离」——文章要写清这个差异，别把两者混成一谈。
2. **篇幅**：逆向 + 教学易超 6000。目标 4000–5500，砍「为什么逆向」铺垫，不砍算法拆解。
3. **uMode 三模式**是「专家级」洞察，需要 `get_shader_info` 常量值坐实 uMode/uCascade 逐级值；读不到就退回「源码 + 管线」两条腿论证。

## 七、一句话主题（定稿主线）

**MCP 能做的不是「读出一个 buffer」，是「读懂一门算法」——打开竞品 Radiance Cascades 的捕获，把整条级联管线扒出来、逐级核对源码、再教给别人。**
