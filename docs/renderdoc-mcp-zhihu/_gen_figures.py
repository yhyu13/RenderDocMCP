# Generate Zhihu PNG figures. Run from anywhere; writes next to this file.
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parent / "images"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
    "font.family": "sans-serif",
    "axes.unicode_minus": False,
    "figure.facecolor": "#f7f4ee",
    "savefig.facecolor": "#f7f4ee",
    "savefig.dpi": 160,
})


def box(ax, x, y, w, h, text, fc="#fffdf8", ec="#3d3a36", lw=1.4, size=11, weight="medium"):
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=2,
    )
    ax.add_patch(p)
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center", fontsize=size, color="#2b2926",
        weight=weight, zorder=3, wrap=True,
    )


def arrow(ax, x1, y1, x2, y2, color="#5a564f"):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>", mutation_scale=12,
        linewidth=1.5, color=color, zorder=1,
    ))


def finish(fig, name):
    fig.tight_layout()
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    print("wrote", path)


def fig_architecture():
    fig, ax = plt.subplots(figsize=(10.2, 6.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.4)
    ax.axis("off")
    ax.set_title("两套 Python，中间只有文件 IPC", fontsize=16, pad=10, color="#2b2926", weight="semibold")

    box(ax, 0.4, 4.7, 9.2, 1.2, "AI 客户端  ·  stdio  ·  Python ≥ 3.10\nKilo / Claude 调 MCP 工具", fc="#e8f1e4", size=12)
    box(ax, 0.4, 2.9, 9.2, 1.35, "MCP 进程  ·  FastMCP  ·  Python ≥ 3.10\nrdc_harness 编排  ·  读穿透缓存  ·  不进 RenderDoc", fc="#e4eef6", size=12)
    box(ax, 0.4, 1.7, 9.2, 0.85, "%TEMP%/renderdoc_mcp/   request.json  <->  response.json  ·  lock  ·  100ms 轮询", fc="#f3ead6", size=11)
    box(ax, 0.4, 0.25, 9.2, 1.2, "qrenderdoc.exe  ·  扩展  ·  内嵌 Python 3.6（stdlib + PySide2）\nReplayController 必须走 BlockInvoke", fc="#f6e4e0", size=12)

    arrow(ax, 5, 4.7, 5, 4.25)
    arrow(ax, 5, 2.9, 5, 2.55)
    arrow(ax, 5, 1.7, 5, 1.45)
    finish(fig, "01-architecture.png")


def fig_loop():
    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.4)
    ax.axis("off")
    ax.set_title("产品闭环：像素必须变，才算替换生效", fontsize=16, pad=10, color="#2b2926", weight="semibold")

    steps = [
        (0.25, 3.15, "1  读源\npick + source"),
        (2.2, 3.15, "2  编译\nBuildTargetShader"),
        (4.15, 3.15, "3  替换\nReplaceResource"),
        (6.1, 3.15, "4  重放\nSetFrameEvent"),
        (8.05, 3.15, "5  验像素\npick_pixel"),
    ]
    for x, y, t in steps:
        box(ax, x, y, 1.75, 1.35, t, fc="#e4eef6", size=10)

    for i in range(4):
        x1 = steps[i][0] + 1.75
        x2 = steps[i + 1][0]
        arrow(ax, x1, 3.82, x2, 3.82)

    box(ax, 0.25, 0.35, 4.55, 2.2,
        "OpenGL frame480  event 550\n\n替换前  [0.011, 0.011, 0.011, 0.945]\n替换后  [1.0, 0.0, 1.0, 1.0]  品红\n撤销后  回到原值",
        fc="#e8f1e4", size=11)
    box(ax, 5.15, 0.35, 4.6, 2.2,
        "不是工具列表变长\n\n编译必须回活 ResourceId\n替换必须在 UI 线程登记\n重放必须真的跑完\n像素必须对得上",
        fc="#fffdf8", size=11)
    finish(fig, "02-product-loop.png")


def fig_bugs():
    fig, ax = plt.subplots(figsize=(10.2, 6.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.0)
    ax.axis("off")
    ax.set_title("三次实锤：API 名字对了，绑定语义仍会撒谎", fontsize=16, pad=10, color="#2b2926", weight="semibold")

    box(ax, 0.3, 4.05, 3.0, 1.55,
        "ResourceId::0\n\nC++ id 是 private\nrid.id = n 仍是 Null",
        fc="#f6e4e0", size=11)
    box(ax, 3.5, 4.05, 3.0, 1.55,
        "GetCaptureFile\n\n在 ReplayManager 上\n不在 CaptureContext",
        fc="#f3ead6", size=11)
    box(ax, 6.7, 4.05, 3.0, 1.55,
        "替换后重放死锁\n\nRegisterReplacement\n进了 replay 线程",
        fc="#e4eef6", size=11)

    box(ax, 0.3, 0.35, 3.0, 3.3,
        "活对象扫描\n+ 编译期缓存\n\nreplace 必须回显\n同一次会话的 id\n不能手拼 ResourceId::N",
        fc="#fffdf8", size=11)
    box(ax, 3.5, 0.35, 3.0, 3.3,
        "pick_capture_access()\n\nReplayManager 优先\n再退回 CaptureContext\n\nlist_sections 看到\n122 MB framecapture",
        fc="#fffdf8", size=11)
    box(ax, 6.7, 0.35, 3.0, 3.3,
        "UI 调用放在\nBlockInvoke 之外\n\n重放走 120s 超时\n\nreplay_event(550)\n返回 {replayed:true}",
        fc="#fffdf8", size=11)
    finish(fig, "03-three-bugs.png")


def fig_ceiling():
    fig, ax = plt.subplots(figsize=(10.2, 5.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    ax.set_title("RenderDoc 是回放调试器，不是编辑器", fontsize=16, pad=10, color="#2b2926", weight="semibold")

    box(ax, 0.35, 0.4, 4.5, 4.6,
        "能做（API 天花板内）\n\n"
        "· 编译 / 替换 shader\n"
        "· 用已有 ResourceId 对换资源\n"
        "· 另存带替换的 .rdc\n"
        "· 导出纹理 / 缓冲 / 节\n"
        "· 写 notes 等小节\n"
        "· 自定义可视化 shader",
        fc="#e8f1e4", size=12)
    box(ax, 5.15, 0.4, 4.5, 4.6,
        "做不到（MCP 也补不上）\n\n"
        "· SetTextureData / SetBufferData\n"
        "· 改 blend / rasterizer / VB\n"
        "  再重新渲染\n"
        "· 驱动目标进程做 live capture\n"
        "· OpenGL 无 debug info 时\n"
        "  步进 debug_pixel",
        fc="#f6e4e0", size=12)
    finish(fig, "04-ceiling.png")


if __name__ == "__main__":
    fig_architecture()
    fig_loop()
    fig_bugs()
    fig_ceiling()
