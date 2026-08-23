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


def box(ax, x, y, w, h, text, fc="#fffdf8", ec="#3d3a36", lw=1.4, size=11, weight="medium", color="#2b2926"):
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=2,
    )
    ax.add_patch(p)
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center", fontsize=size, color=color,
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


def fig_wrong():
    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.4)
    ax.axis("off")
    ax.set_title("错路是把面板都做成工具；正路是像素必须变", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.3, 0.85, 4.5, 4.05,
        "错路\n\n每个面板做成一个工具\n工具很快超过五十个\nJSON 回显也是绿的",
        fc="#f6e4e0", size=13)
    ax.text(2.55, 0.45, "不是产品", ha="center", va="center", fontsize=13, color="#b42318", weight="semibold")
    box(ax, 5.2, 0.85, 4.5, 4.05,
        "正路\n\n改一段着色器，重放一帧\n灰变成品红，撤销回到原值",
        fc="#e8f1e4", size=13)
    ax.text(7.45, 0.45, "才是产品", ha="center", va="center", fontsize=13, color="#1f6b3a", weight="semibold")
    finish(fig, "00-wrong-right.png")


def fig_thread():
    fig, ax = plt.subplots(figsize=(10.2, 5.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.8)
    ax.axis("off")
    ax.set_title("脉络：拆厨房 → 钉闭环 → 修身份证 → 认天花板", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    steps = [
        (0.25, 3.35, "需求\n像素变了\n才算做成"),
        (2.2, 3.35, "接缝\n两间厨房\n中间递纸条"),
        (4.15, 3.35, "树根\n用活身份证\n去对的抽屉"),
        (6.1, 3.35, "主干\n两间屋子\n不许互相等"),
        (8.05, 3.35, "切开\n回放台\n不是编辑器"),
    ]
    for x, y, t in steps:
        box(ax, x, y, 1.75, 1.75, t, fc="#e4eef6", size=10)
    for i in range(4):
        arrow(ax, steps[i][0] + 1.75, 4.2, steps[i + 1][0], 4.2)
    box(ax, 0.25, 0.35, 9.5, 2.5,
        "每一步的「不是什么」\n\n"
        "需求不是工具变多　　接缝不是共用一个灶台\n"
        "树根不是手填编号　　主干不是把前台的活塞进后厨\n"
        "切开不是往底片上写新像素，也不是改完灯光再拍一遍",
        fc="#fffdf8", size=12)
    finish(fig, "00-thread.png")


def fig_tree():
    fig, ax = plt.subplots(figsize=(10.2, 6.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.2)
    ax.axis("off")
    ax.set_title("树：树根是活身份证，主干是两间屋子，枝叶才是工具", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 1.6, 4.9, 6.8, 0.95, "树根  ·  用捕获里的活身份证，去拿着文件的那只手\n不是手填编号，不是在错误的抽屉里找文件", fc="#f3ead6", size=12)
    box(ax, 1.6, 3.5, 6.8, 0.95, "主干  ·  前台的登记，不要派进后厨那条线\n否则两间屋子互相等，整栋楼停摆", fc="#e4eef6", size=12)
    box(ax, 0.25, 0.35, 3.0, 2.7, "枝：看\n\n点一个像素\n看谁写过它\n对一下网格", fc="#e8f1e4", size=12)
    box(ax, 3.5, 0.35, 3.0, 2.7, "枝：改\n\n编译着色器\n换上再重放\n验像素", fc="#e8f1e4", size=12)
    box(ax, 6.75, 0.35, 3.0, 2.7, "枝：带走\n\n导出图和缓冲\n另存这份捕获\n写一小段笔记", fc="#e8f1e4", size=12)
    arrow(ax, 5, 4.9, 5, 4.45)
    finish(fig, "05-tree.png")


def fig_architecture():
    fig, ax = plt.subplots(figsize=(10.2, 6.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.4)
    ax.axis("off")
    ax.set_title("两间厨房，中间只递纸条，不要共用一个灶台", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.4, 4.75, 9.2, 1.15, "外面那间  ·  现代 Python  ·  AI 客户端\n负责编排、缓存、说话", fc="#e8f1e4", size=12)
    box(ax, 0.4, 3.0, 9.2, 1.25, "中间  ·  临时目录里三张纸条\n请求、应答、正在写  ·  百分之一秒看一次", fc="#f3ead6", size=12)
    box(ax, 0.4, 0.35, 9.2, 2.15, "里面那间  ·  调试器自带的老 Python\n没有网口，回放必须派到指定那条线再等它做完", fc="#f6e4e0", size=12)
    ax.text(5, 2.65, "不是：改成网口  ·  也不是：把外面的库塞进里面", ha="center", va="center", fontsize=12, color="#b42318", weight="semibold")
    arrow(ax, 5, 4.75, 5, 4.25)
    arrow(ax, 5, 3.0, 5, 2.5)
    finish(fig, "01-architecture.png")


def fig_loop():
    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.4)
    ax.axis("off")
    ax.set_title("五步闭环：像素必须变，才算替换生效", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    steps = [
        (0.25, 3.2, "1  读源"),
        (2.2, 3.2, "2  编译"),
        (4.15, 3.2, "3  换上"),
        (6.1, 3.2, "4  重放"),
        (8.05, 3.2, "5  验像素"),
    ]
    for x, y, t in steps:
        box(ax, x, y, 1.75, 1.2, t, fc="#e4eef6", size=12)
    for i in range(4):
        arrow(ax, steps[i][0] + 1.75, 3.8, steps[i + 1][0], 3.8)
    box(ax, 0.25, 0.35, 9.5, 2.4,
        "同一中心像素，同一份捕获，测过两轮\n\n灰  →  品红  →  撤销回到灰\n调试器没死，纸条没卡住",
        fc="#e8f1e4", size=13)
    finish(fig, "02-product-loop.png")


def fig_evidence():
    fig, ax = plt.subplots(figsize=(10.2, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.0)
    ax.axis("off")
    ax.set_title("「我替换了」不算完。听像素。", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.3, 1.6, 2.9, 2.8, "替换前\n\n灰", fc="#eceae4", size=16, weight="semibold")
    box(ax, 3.55, 1.6, 2.9, 2.8, "替换后\n\n品红", fc="#f3d6ee", size=16, weight="semibold")
    box(ax, 6.8, 1.6, 2.9, 2.8, "撤销后\n\n灰", fc="#eceae4", size=16, weight="semibold")
    ax.text(5, 0.7, "不是：接口回了一段成功 JSON", ha="center", va="center", fontsize=13, color="#b42318", weight="semibold")
    finish(fig, "09-evidence-pixel.png")


def fig_empty():
    fig, ax = plt.subplots(figsize=(10.2, 5.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    ax.set_title("空等于空，会误报「找到了」", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.35, 2.55, 4.4, 2.15, "没绑着色器的阶段\n身份证是空", fc="#f6e4e0", size=14)
    box(ax, 5.25, 2.55, 4.4, 2.15, "手填出来的编号\n其实也是空", fc="#f6e4e0", size=14)
    box(ax, 2.0, 0.4, 6.0, 1.7, "两边一比：空 = 空\n于是每个没绑的阶段都报命中", fc="#fffdf8", size=14)
    ax.text(5, 2.2, "不是「对上了」", ha="center", va="center", fontsize=13, color="#b42318", weight="semibold")
    finish(fig, "07-empty-eq-empty.png")


def fig_drawer():
    fig, ax = plt.subplots(figsize=(10.2, 5.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    ax.set_title("文件在另一只手上，不要翻错抽屉", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.35, 1.5, 4.4, 3.2, "错的抽屉\n\n打开捕获的那个上下文\n问它要文件\n拿到的是空", fc="#f6e4e0", size=13)
    box(ax, 5.25, 1.5, 4.4, 3.2, "对的那只手\n\n真正管回放的那一层\n文件句柄在这里", fc="#e8f1e4", size=13)
    ax.text(5, 0.7, "不是：打开了捕获，就等于拿着文件", ha="center", va="center", fontsize=13, color="#b42318", weight="semibold")
    finish(fig, "10-wrong-drawer.png")


def fig_rooms():
    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.4)
    ax.axis("off")
    ax.set_title("前台的登记，不要派进后厨。两间屋子会互相等。", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.35, 2.3, 4.4, 2.55, "前台  ·  界面那条线\n登记「换上了」\n等人看见", fc="#e4eef6", size=14)
    box(ax, 5.25, 2.3, 4.4, 2.55, "后厨  ·  回放那条线\n真正换着色器\n再重放这一帧", fc="#f3ead6", size=14)
    ax.annotate("", xy=(5.25, 3.2), xytext=(4.75, 3.2),
                arrowprops=dict(arrowstyle="<|-|>", color="#b42318", lw=2))
    ax.text(5, 1.55, "后厨等前台，前台等后厨", ha="center", va="center", fontsize=13, color="#b42318", weight="semibold")
    box(ax, 1.5, 0.3, 7.0, 0.95, "空重放没换东西，是好的。带真替换再重放才会炸。", fc="#fffdf8", size=12)
    finish(fig, "08-two-rooms.png")


def fig_bugs():
    fig, ax = plt.subplots(figsize=(10.2, 5.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    ax.set_title("三次实锤：名字对了，语义仍会撒谎", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.3, 3.15, 3.0, 2.0, "手填编号\n看起来有数字\n比较时仍是空", fc="#f6e4e0", size=13)
    box(ax, 3.5, 3.15, 3.0, 2.0, "翻错抽屉\n打开了捕获\n文件在另一只手", fc="#f3ead6", size=13)
    box(ax, 6.7, 3.15, 3.0, 2.0, "活派错屋\n前台登记\n进了后厨", fc="#e4eef6", size=13)
    box(ax, 0.3, 0.35, 3.0, 2.4, "对活身份证\n编译出来的那个\n当场记住", fc="#fffdf8", size=12)
    box(ax, 3.5, 0.35, 3.0, 2.4, "去管回放的\n那一层拿文件", fc="#fffdf8", size=12)
    box(ax, 6.7, 0.35, 3.0, 2.4, "登记放在\n后厨做完之后", fc="#fffdf8", size=12)
    finish(fig, "03-three-bugs.png")


def fig_ceiling():
    fig, ax = plt.subplots(figsize=(10.2, 5.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    ax.set_title("这是回放台，不是编辑器。MCP 补不上缺口。", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.35, 0.85, 4.5, 4.2,
        "能做\n\n"
        "换一份着色器再看\n"
        "用已经存在的资源对换\n"
        "另存、导出、写一小段笔记",
        fc="#e8f1e4", size=13)
    box(ax, 5.15, 0.85, 4.5, 4.2,
        "做不到\n\n"
        "往底片上写新像素\n"
        "改完灯光再拍一遍\n"
        "替游戏重新录一帧",
        fc="#f6e4e0", size=13)
    ax.text(5, 0.4, "缺口在调试器，不在接线层", ha="center", va="center", fontsize=13, color="#b42318", weight="semibold")
    finish(fig, "04-ceiling.png")


def fig_cache():
    fig, ax = plt.subplots(figsize=(10.2, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.0)
    ax.axis("off")
    ax.set_title("同一份捕获、同一个问题，不该每次都进后厨", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.35, 2.4, 4.4, 2.15, "只读、问过了\n记在外面那间厨房", fc="#e8f1e4", size=14)
    box(ax, 5.25, 2.4, 4.4, 2.15, "刚改过、会排空、在导出\n不要记，直接进后厨", fc="#f6e4e0", size=14)
    box(ax, 1.2, 0.35, 7.6, 1.6, "缓存进不了调试器里面。那是老灶台，放不下外面的锅。", fc="#fffdf8", size=13)
    finish(fig, "11-cache.png")


def fig_why():
    fig, ax = plt.subplots(figsize=(10.2, 5.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    ax.set_title("RenderDoc 是验收场，不是目的地", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    box(ax, 0.3, 3.15, 4.55, 2.0, "要验收的\n\nAgent 驾驭层：跨轮不改题\n听像素，不听口头成功", fc="#e8f1e4", size=13)
    box(ax, 5.15, 3.15, 4.55, 2.0, "不是要验收的\n\n再做一个调试器插件\n把面板都做成工具", fc="#f6e4e0", size=13)
    box(ax, 0.3, 0.4, 9.4, 2.4,
        "真机器、老灶台、会死锁的回放\n题目必须钉住，空了接着干，像素变了才算完",
        fc="#fffdf8", size=14)
    finish(fig, "12-why-harness.png")


def fig_takeaway():
    fig, ax = plt.subplots(figsize=(10.2, 6.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.2)
    ax.axis("off")
    ax.set_title("能搬走的是切割，不是五十个工具名", fontsize=16, pad=10, color="#2b2926", weight="semibold")
    items = [
        (0.3, 4.3, "1  两间厨房，中间递纸条\n不是共用一个灶台"),
        (5.15, 4.3, "2  用活身份证，去对的抽屉\n不是手填编号"),
        (0.3, 2.35, "3  前台登记不要派进后厨\n否则两间屋子互相等"),
        (5.15, 2.35, "4  听像素，不听口头成功\n灰变品红才算完"),
        (0.3, 0.4, "5  回放台不是编辑器\n缺口补不上"),
        (5.15, 0.4, "6  驾驭层听像素不听口头\n题目跨轮不许改小"),
    ]
    for x, y, t in items:
        box(ax, x, y, 4.55, 1.6, t, fc="#fffdf8", size=12)
    finish(fig, "06-takeaway.png")


if __name__ == "__main__":
    fig_why()
    fig_wrong()
    fig_thread()
    fig_tree()
    fig_architecture()
    fig_loop()
    fig_evidence()
    fig_bugs()
    fig_empty()
    fig_drawer()
    fig_rooms()
    fig_ceiling()
    fig_cache()
    fig_takeaway()
