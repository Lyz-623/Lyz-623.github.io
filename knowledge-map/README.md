PC-TWINS 知识地图（knowledge map）
==================================

一个纯静态的子页面：把二维电子光谱（2DES）与 PC-TWINS 课题拆成 23 个按依赖分层的模块，
按知识组织而不是学习进度：页面只有三部分——分层依赖图（点击模块高亮其前置与后续）、
每个模块一张知识卡片（3–6 条核心概念、2–5 个关键结果与公式、2–5 条经核实的推荐阅读），
以及可搜索的术语卡片（中文、英文、一句话定义）。线上地址（推送后）：
<https://lyz-623.github.io/knowledge-map/>

文件
----

```text
knowledge-map/
├── index.html    页面骨架（复用 ../assets/main.css 的字体、配色和组件）
├── kmap.css      本页专用样式（图谱、知识卡片、术语卡片）
├── kmap.js       渲染与交互（SVG 依赖图、知识卡片面板、术语搜索、KaTeX 排版）
├── data.js       由 gen_data.py 生成，不要手改
├── gen_data.py   全部内容与校验逻辑：以后只改这个文件
└── README.md
```

没有构建工具。公式用 KaTeX 渲染，固定为 jsDelivr 上的 `katex@0.16.11`
（`katex.min.css`、`katex.min.js`、`contrib/auto-render.min.js`，带 SRI）；每次更新知识卡片或
术语搜索结果后都会调用 `renderMathInElement`。`data.js` 以普通 `<script>` 引入，直接双击
`index.html`（file://）也能打开（公式需要能访问 CDN）。

本地预览
--------

在仓库根目录运行：

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m http.server 8000
```

然后打开 <http://localhost:8000/knowledge-map/>。用本地服务器预览时，页面顶部
“主页”链接和主页上的项目卡片都能正常跳转。

修改内容并重新生成
------------------

所有模块、知识卡片、文献和术语都在 `gen_data.py` 中：

- `REFS`：文献表。每条写作者、标题、出处、年份，以及 `doi`、`arxiv` 或 `url`
  之一。无法核实的条目加 `status="unverified"` 和 `note`，页面会显示“未能核实”。
- `MODULES`：模块列表。`concepts` 是核心概念，`F(名称, LaTeX, 说明)` 是关键结果与公式，
  `R(文献键, 类型, 优先级, 读哪部分, 为什么)` 是推荐阅读，`T(中文, 英文, 定义)` 是术语卡片。
- 公式一律写 LaTeX：普通文字中用 `$...$`（如 `$V=(I_{\max}-I_{\min})/(I_{\max}+I_{\min})$`），
  `F(...)` 的公式字段写不带 `$` 的裸 LaTeX，页面以行间公式显示。建议用 `r"..."` 字符串。

改完后运行：

```powershell
cd knowledge-map
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" gen_data.py          # 校验并写入 data.js
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" gen_data.py --check  # 只校验
```

校验失败时不会写文件，并以非零状态退出。检查项包括：依赖图无环且每个前置位于更低的层；
模块 ID 与术语不重复；每个模块 3–6 条核心概念、2–5 个关键结果、2–5 条阅读且至少一条“首读”、
3–6 张术语卡片；文献键存在；数学写法合规（`$` 与花括号配对、公式内无中文、`$...$` 之外不出现
希腊字母、上下标数字、`_`、`^` 等数学符号）；教材章节在 0–40 之内。

检查链接
--------

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" gen_data.py --check-links
```

逐条在线检查：DOI 先查 Crossref（`https://api.crossref.org/works/<DOI>`），Crossref
没有或无标题的（如 DataCite 的 10.6082、figshare 的 10.6084）改用 doi.org 内容协商；
arXiv 编号查 arXiv API；普通网页检查 HTTP 200 以及页面中是否含预期文字。报告会比对标题和年份，
任何一项失败则以非零状态退出，最后列出页面上标为“未能核实”的条目。

部署到 GitHub Pages
-------------------

本目录位于主页仓库 `Lyz-623/Lyz-623.github.io` 中，随主页一起由 GitHub Pages 发布，无需额外配置
（仓库根目录已有 `.nojekyll`）。流程：

1. 修改 `gen_data.py`，运行 `gen_data.py` 与 `gen_data.py --check-links`；
2. 本地预览确认无误；
3. 提交 `gen_data.py` 与新生成的 `data.js`，推送到 `master`；
4. 若改了 `kmap.css` / `kmap.js` / `data.js`，同步更新 `index.html` 中的 `?v=` 版本号，避免浏览器缓存旧文件。

隐私
----

页面不保存任何学习记录；唯一的本地存储是与主页共用的主题偏好 `yunze-theme`。
