PC-TWINS 学习路线图（knowledge map）
====================================

一个纯静态的子页面：把二维电子光谱（2DES）与 PC-TWINS 课题拆成 23 个按依赖分层的模块，
每个模块给出前置依赖、为什么学、对应教材章节、建议周次、6–8 条可勾选的掌握清单、
2–5 条经核实的推荐阅读和 3–6 个术语。线上地址（推送后）：
<https://lyz-623.github.io/knowledge-map/>

文件
----

```text
knowledge-map/
├── index.html    页面骨架（复用 ../assets/main.css 的字体、配色和组件）
├── kmap.css      本页专用样式（图谱、清单、时间线、术语表）
├── kmap.js       渲染与交互（SVG 依赖图、详情面板、进度、导入导出、搜索）
├── data.js       由 gen_data.py 生成，不要手改
├── gen_data.py   全部内容与校验逻辑：以后只改这个文件
└── README.md
```

没有构建工具，也不依赖任何外部库；`data.js` 以普通 `<script>` 引入，所以直接双击
`index.html`（file://）也能打开。

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

所有模块、清单、文献和术语都在 `gen_data.py` 中：

- `REFS`：文献表。每条写作者、标题、出处、年份，以及 `doi`、`arxiv` 或 `url`
  之一。无法核实的条目加 `status="unverified"` 和 `note`，页面会显示“未能核实”。
- `MODULES`：模块列表。`C(层级, 文字)` 是清单条目，`R(文献键, 类型, 优先级, 读哪部分, 为什么)`
  是推荐阅读，`T(中文, 英文, 定义)` 是术语。
- `weeks=(起, 止)` 与 `hours` 决定 26 周计划；校验会把学时按周均摊并要求每周 15–20 小时。

改完后运行：

```powershell
cd knowledge-map
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" gen_data.py          # 校验并写入 data.js
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" gen_data.py --check  # 只校验
```

校验失败时不会写文件，并以非零状态退出。检查项包括：依赖图无环且每个前置位于更低的层；
模块 ID、清单条目、术语不重复；每个模块 6–8 条清单（以“能…/知道…”开头，不能写“理解/掌握”）、
2–5 条阅读且至少一条“首读”、3–6 个术语；模块只能在全部前置结束之后开始；每周学时 15–20 小时；
教材章节在 0–40 之内（未覆盖的章节会给出警告）。

勾选进度按条目文字的哈希保存（如 `F3-3149e9`）。改写某条清单的文字会让这一条的勾选失效；
如果只是改措辞又想保留进度，可在 `C(...)` 中加 `key="旧哈希"`。

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

进度只保存在访问者自己浏览器的 `localStorage`（键名 `kmap-progress-v1`），不会上传；
主题偏好与主页共用 `yunze-theme` 键。
