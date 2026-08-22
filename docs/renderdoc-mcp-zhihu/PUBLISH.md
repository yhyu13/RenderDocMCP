# 知乎专栏粘贴说明

知乎不渲染 mermaid，也不显示 SVG。本文配图已是 PNG。知乎开放平台 CLI（`zhihu-cli`）只能读本人创作，**不能发文或改文**；发布仍是编辑器粘贴。

## 标题

给 AI 接 RenderDoc，真正的产品不是工具列表

## 导语（30–40 字，可作开头摘要）

五十个 MCP 工具仍不是产品。产品是：在已打开的 .rdc 里改 shader、重放、像素真的变了。

## 配图上传顺序

1. `images/01-architecture.png` — 两套 Python，中间只有文件 IPC
2. `images/02-product-loop.png` — 五步闭环，像素必须变
3. `images/03-three-bugs.png` — ResourceId::0 / GetCaptureFile / 替换后死锁
4. `images/04-ceiling.png` — 回放调试器的能做 / 做不到

正文里的 `![…](images/….png)` 粘贴后不会自动带上本地文件；在对应位置插入刚上传的图即可。

## 标签建议

RenderDoc、图形调试、MCP、AI Agent、OpenGL

## 仓库

https://github.com/yhyu13/RenderDocMCP
