# fields-study-flow

## 最新功能快速说明

- 单篇论文路线现在会额外生成 `paper_lens.html`，这是一个独立的“目标论文增强阅读器”。
- `paper_lens.html` 会按摘要、背景、方法、公式、实验、局限和相关工作组织阅读卡片，并把资料包中的论文、书籍、代码、网页快照和 RAG 证据片段挂回对应章节。
- 使用 `--resource-dir` 时，`roadmap.html`、`paper_lens.html` 和 `roadmap.md` 会优先链接到本地已下载/复制资料；未下载或仅链接资料才保留原始网络入口。
- 如果只想保留路线报告，可以在 `paper` 或 `roadmap` 命令中加入 `--no-paper-lens`。
- 共享型 JSON/HTML/MD 仍会隐藏 `C:\...`、`D:\...` 等本地绝对路径，只保留相对本地链接或脱敏标识。

简体中文 | [English](README.md)

面向 AI/CS 论文、领域和课程学习的 agent-native 掌握路径生成器。

fields-study-flow 可以把“掌握这篇论文”“学习 diffusion models”“复现 YOLO”这类目标，转成一条可追踪、可验证的学习路径。它会综合学习者画像、路线深度、语言偏好、开放来源实时搜索和显式提供的本地资源，最后导出 Markdown、JSON、SVG 和美观的静态 HTML 报告。

<p align="center">
  <img src="docs/assets/fields-study-flow-architecture-zh.svg" alt="fields-study-flow 架构图" width="100%">
</p>

## 它优化什么

- 统一双模式：单篇论文掌握和领域/课程学习共用同一个 planner。
- 掌握标准：讲清楚、推导关键点、复现核心方法、批判局限。
- 路线深度：`fastest`、默认 `balanced`、或 `complete`。
- 学习风格：默认实战复现优先，也支持理论优先、视频优先和自动模式。
- 语言选择：Markdown、HTML、SVG 报告会遵循 `zh-CN`、`en` 或 `bilingual` 输出语言。
- 最短路线：`fastest` 和实战型 `balanced` 会把宽泛前置课程压缩成紧贴目标的前置冲刺。
- 本地资源：只分析用户显式传入的路径，共享输出中不暴露本地绝对路径。
- 论文解析：本地 PDF 会尽量抽取章节、方法/实验/局限提示、关键词、公式候选和代码链接。
- RAG 证据路线：目标论文、本地资源和资料包会被切分成轻量证据片段，写入 `.rag_index`，关键点、推荐理由和验收任务都可以引用来源片段。
- 学习知识图谱：报告会展示本地轻量的 concept -> resource -> task -> assessment 图谱，用于导航和掌握追踪。
- 实时搜索：默认搜索开放官方 API；需要凭证或只适合手动链接的平台不会被自动抓取。
- 路线审计：每条路线都会说明覆盖度、省略资源、节省耗时，以及为什么这是当前候选和路线深度下的最短可行路径。
- 可执行任务：报告包含学习任务、下一步行动、质量门、最终证据和可运行产物验收。
- 交互式学习中控台：`roadmap.html` 是主报告入口，提供可拖动/缩放的 KG 学习路径网络、右侧任务向导、本地进度勾选、本地优先资料链接、多维资料筛选 chips、证据展开/收起和阶段折叠。

## 快速开始

```bash
python -m pip install -e .
fields-study-flow roadmap \
  --goal "学习 diffusion models 并做一个小项目" \
  --preset field-project \
  --output-language zh-CN \
  --resource-language en-first \
  --local-resource ./my-notes/diffusion \
  --resource-dir ./study-assets/diffusion \
  --bundle-scope all
```

如果不希望实时搜索，可以使用确定性的离线模式：

```bash
fields-study-flow roadmap \
  --goal "掌握 Transformer 论文" \
  --no-live-search \
  --local-resource ./my-notes/transformer
```

论文深读路线：

```bash
fields-study-flow paper \
  --url https://arxiv.org/abs/1706.03762 \
  --preset paper-fastest \
  --output-language bilingual \
  --resource-language en-first \
  --resource-dir ./study-assets/transformer
```

交互向导会先询问语言、存储、学习偏好；如果启用资料包，也会继续询问 `bundle_scope`，再执行规划：

```bash
fields-study-flow paper --interactive
fields-study-flow roadmap --interactive
```

生成文件：

```text
fields-study-flow-output/
  learner_profile.json
  resource_index.json
  local_resource_analysis.json
  source_registry_snapshot.json
  roadmap.md
  roadmap.json
  roadmap.svg
  roadmap.html            # 主交互式学习报告
  artifact_template/        # 仅在需要可运行项目或复现验收时生成
    README.md
    task_checklist.md
    reproduction_log.md
    notebook_skeleton.ipynb
    src/main.py

study-assets/
  study_bundle_manifest.json # 设置 --resource-dir 时生成
  README.md                   # 资料包摘要和开始学习说明
  .rag_index/manifest.json   # 用于证据检索和资料包问答
  links.md
  01-selected-local-or-open-resource.pdf
```

使用 `--resource-dir` 时，`roadmap.html` 和 `roadmap.md` 中已下载/复制的资料会优先链接到本地资料包。原始网页链接仍作为来源或兜底入口展示，共享型输出仍不会暴露本地绝对路径。

只基于已经下载/复制的资料包提问：

```bash
fields-study-flow ask \
  --roadmap fields-study-flow-output/roadmap.json \
  --resource-dir ./study-assets/diffusion \
  --question "哪些证据解释了复现目标？"
```

## 关键参数

| 参数 | 含义 |
| --- | --- |
| `--preset fastest\|balanced\|complete\|paper-fastest\|paper-deep\|field-project\|course-complete` | 使用常见学习模式快速启动；显式参数仍可覆盖 preset。 |
| `--target-kind paper\|field\|course\|auto` | 指定或自动判断论文、领域、课程模式。 |
| `--route-depth fastest\|balanced\|complete` | 控制路线是最短、平衡还是最完整。 |
| `--learning-style practical\|theory\|video\|auto` | 控制资源排序偏向实战、理论或直觉材料。 |
| `--local-resource PATH` | 分析显式提供的本地文件或文件夹，可重复传入。 |
| `--resource-dir PATH` | 将学习资料库复制/下载到私有资料目录，并写出 `study_bundle_manifest.json`。 |
| `--bundle-scope selected\|all` | 控制资料包只下载最短路线资料，还是尝试下载全部可直接获取的候选资料。默认是 `all`；不可获取的资料仍会进入 `links.md`。 |
| `--rag off\|light\|auto\|embedding` | 控制证据检索模式。`auto` 使用轻量本地检索；`embedding` 在安装可选 `rag` extra 后启用。 |
| `--interactive` | 先询问目标、语言、路线深度、学习风格、本地资源、报告目录和资料目录，再执行。 |
| `--no-live-search` / `--offline` | 关闭默认实时搜索，使用确定性目录和显式资源。 |
| `--output-language zh-CN\|en\|bilingual` | 控制路线输出语言。 |
| `--resource-language zh-first\|en-first\|balanced\|zh-only\|en-only` | 控制资料语言偏好。 |

本地资源支持 Markdown、TXT、TeX、PDF、Jupyter Notebook、Python、YAML/JSON/CSV，以及常见文档和课件格式的元数据级分析。资料打包只复制用户显式提供的路径。默认 `--bundle-scope all` 会尝试下载全部可直接获取的候选资料，包括 arXiv PDF、GitHub raw 文件、公开 GitHub 仓库归档，以及服务器允许时的普通公开网页 HTML 快照；`--bundle-scope selected` 则保留更快的最短路线资料包行为。视频、受限页面、失败下载和需要凭证的来源会保留在 `links.md` 中，manifest 会记录 selected/omitted 以及 downloaded/link-only 状态。

embedding 检索是可选增强：

```bash
python -m pip install -e .[rag]
```

## MCP 风格工具

运行 JSON-lines 工具服务：

```bash
python -m fields_study_flow.mcp_server
```

示例：

```json
{"tool":"searchResources","arguments":{"query":"Transformer derivation","languagePreference":"en-first"}}
```

可用函数：

- `assessKnowledge`
- `discoverSources`
- `searchResources`
- `analyzeLocalResources`
- `ingestUrl`
- `rankResources`
- `buildRoadmap`
- `retrieveEvidence`
- `answerFromBundle`
- `validateSources`
- `exportPlan`

`exportPlan` 会写出 JSON、Markdown、SVG、HTML；当路线需要可运行项目或复现验收时，还会写出 `artifact_template/` 模板包。
模板包会遵循所选输出语言；如果有论文解析结果，也会写入公式、代码链接、实验和局限相关验收目标。

交互式 HTML 是单个可离线打开的文件，不依赖前端框架、远程字体或在线脚本。任务进度会在浏览器允许时写入 `localStorage`；如果浏览器阻止本地存储，报告仍然可以阅读和点击，只是勾选状态作为临时状态处理。

在 Windows PowerShell 中读取导出的 JSON 时，建议显式使用 UTF-8：

```powershell
Get-Content .\fields-study-flow-output\roadmap.json -Raw -Encoding UTF8 | ConvertFrom-Json
```

## 架构

```text
目标/画像
  -> 统一规划参数
  -> 实时搜索 + 离线目录 + 显式本地资源
  -> 轻量 RAG chunk + 证据检索
  -> 轻量学习知识图谱
  -> 排序、去重、质量/风格加权
  -> 按路线深度选择掌握路径
  -> 掌握图谱 + 路线审计 + 质量门 + 最终产出 + 检查点
  -> Markdown / JSON / SVG / HTML 输出 + 可选验收模板包
```

核心模块：

```text
fields_study_flow/
  live_search.py      # 开放 API 搜索与凭证安全降级
  local_resources.py  # 显式本地路径分析
  paper_metadata.py   # arXiv/DOI/本地 PDF 元数据与降级解析
  artifact_templates.py # 缺少可运行资源时生成验收模板
  rag.py              # 本地证据片段、资料包索引、检索和资料包问答
  knowledge_graph.py  # 本地概念/资源/任务/验收学习图谱
  ranking.py          # 质量、语言、耗时、学习风格评分
  roadmap.py          # 掌握图谱、路线选择和渲染器
  mcp_tools.py        # agent 可调用函数
  cli.py              # 命令行入口
```

## 安全边界

fields-study-flow 只推荐、摘要和链接资源。它不会默认扫描本地磁盘，不会在共享输出中暴露私有路径，不会绕过登录或付费墙，不会下载视频，不会使用盗版镜像，也不会复制长篇版权内容。所有外部内容都应被视为不可信来源材料。

## 开发

```bash
python -m pip install -e .[dev]
pytest -q
```

MIT。见 [LICENSE](LICENSE)。
