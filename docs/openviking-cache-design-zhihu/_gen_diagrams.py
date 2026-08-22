import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT = "images"


def box(ax, x, y, w, h, text, fc="#EEF3FB", ec="#2F5A91", fs=11, bold=False):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.008",
            linewidth=1.3, edgecolor=ec, facecolor=fc,
        )
    )
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center", fontsize=fs,
        fontweight="bold" if bold else "normal", color="#1a1a1a",
    )


def arrow(ax, x1, y1, x2, y2, color="#2F5A91"):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1), (x2, y2),
            arrowstyle="-|>", mutation_scale=14,
            linewidth=1.5, color=color,
        )
    )


# 01 - data flow
fig, ax = plt.subplots(figsize=(8.2, 4.6), dpi=150)
ax.set_xlim(0, 10)
ax.set_ylim(0, 6)
ax.axis("off")
box(ax, 0.2, 2.0, 2.1, 1.4, "AI 客户端\nMCP 工具调用", fc="#EAF2E0", ec="#4F7A3D")
box(ax, 4.0, 4.0, 2.1, 1.4, "响应缓存\nResponseCache", fc="#EEF3FB", ec="#2F5A91", bold=True)
box(ax, 4.0, 0.8, 2.1, 1.4, "内存 / OpenViking\n后端", fc="#F6EEE8", ec="#9A5B2E")
box(ax, 7.8, 2.6, 2.0, 1.4, "RenderDoc\n文件 IPC + GPU", fc="#F4E6EC", ec="#8F3B58")
arrow(ax, 2.3, 3.0, 4.0, 4.3)
arrow(ax, 4.0, 4.0, 7.8, 3.3)
arrow(ax, 5.05, 4.0, 5.05, 2.2)
arrow(ax, 4.0, 1.5, 4.0, 0.8, color="#9A5B2E")
ax.text(5.15, 3.0, "命中直接返回", fontsize=9, color="#2F5A91")
ax.text(1.25, 4.3, "读请求", fontsize=9, color="#4F7A3D")
ax.text(6.35, 4.35, "未命中读后端", fontsize=9, color="#8F3B58")
ax.text(5.2, 1.6, "缓存键/值", fontsize=9, color="#9A5B2E")
plt.tight_layout()
plt.savefig(f"{OUT}/01-dataflow.png", bbox_inches="tight", facecolor="white")
plt.close()

# 02 - key composition
fig, ax = plt.subplots(figsize=(8.4, 3.6), dpi=150)
ax.set_xlim(0, 12)
ax.set_ylim(0, 5)
ax.axis("off")
parts = [
    ("捕获身份", "path + mtime + size", "#EAF2E0", "#4F7A3D"),
    ("方法名", "get_pipeline_state ...", "#EEF3FB", "#2F5A91"),
    ("规范化参数", "sort_keys JSON", "#F6EEE8", "#9A5B2E"),
]
x = 0.3
for title, sub, fc, ec in parts:
    box(ax, x, 2.0, 2.9, 1.4, f"{title}\n{sub}", fc=fc, ec=ec, fs=10)
    x += 3.2
arrow(ax, 3.2, 2.7, 3.5, 2.7)
arrow(ax, 6.4, 2.7, 6.7, 2.7)
box(ax, 9.3, 2.0, 2.4, 1.4, "SHA-256\n缓存键", fc="#F4E6EC", ec="#8F3B58", bold=True)
ax.text(6.0, 0.9, "没有捕获身份，两个 .rdc 里相同的 event_id 会互相串数据", fontsize=9.5, ha="center", color="#8F3B58")
plt.tight_layout()
plt.savefig(f"{OUT}/02-key.png", bbox_inches="tight", facecolor="white")
plt.close()

# 03 - three categories
fig, ax = plt.subplots(figsize=(8.4, 4.4), dpi=150)
ax.set_xlim(0, 12)
ax.set_ylim(0, 6)
ax.axis("off")
box(ax, 0.2, 2.8, 3.2, 1.8, "确定性只读\n（缓存）\nget_pipeline_state", fc="#EAF2E0", ec="#4F7A3D")
box(ax, 4.4, 2.8, 3.2, 1.8, "改变状态\n（绕过 + 清缓存）\nreplace_shader", fc="#F4E6EC", ec="#8F3B58")
box(ax, 8.6, 2.8, 3.2, 1.8, "排空队列/导出/调试\n（绕过，不清缓存）\nget_debug_messages", fc="#EEF3FB", ec="#2F5A91")
ax.text(1.8, 1.3, "命中不碰 IPC/GPU", fontsize=9.5, ha="center", color="#4F7A3D")
ax.text(6.0, 1.3, "写后旧读数作废", fontsize=9.5, ha="center", color="#8F3B58")
ax.text(10.2, 1.3, "绝不能缓存", fontsize=9.5, ha="center", color="#2F5A91")
plt.tight_layout()
plt.savefig(f"{OUT}/03-categories.png", bbox_inches="tight", facecolor="white")
plt.close()

print("done")
