# Git-4-Study Flow

简体中文 | [English](README.md)

面向 AI/CS 研究者、工程师和学生的 agent-native 学习路线生成器。

Git-4-Study Flow 可以把“读懂这篇论文”、“学习 Transformer”、“复现 YOLO”这类模糊目标，转成一条结构化、可追踪、可继续迭代的学习路线。它会先了解你的已有知识、语言偏好和时间预算，再从论文、GitHub、课程、视频、实践平台和中文社区中整理资源，按难度、可信度和前置知识排序，最后导出 Markdown 与 JSON。

> 为 Codex、Claude Code、Cursor、VS Code 以及任何可调用 CLI/MCP 工具的 agent 设计。

## 为什么做这个项目

很多学习路线生成工具只会给出一串“看起来合理”的链接。Git-4-Study Flow 把真正影响学习质量的部分显式建模：

- 学习者画像：你会什么、卡在哪里、每周能投入多久；
- 语言策略：路线语言和资料语言分开控制；
- 来源注册表：GitHub、论文库、视频平台、公开课程、实践平台、中文社区都有明确规则；
- 排序依据：每个资源都有难度、覆盖概念、可信度、访问说明和推荐理由；
- Agent 工作流：skills 负责访谈和流程，工具层负责稳定生成输出。

## 核心功能

| 能力 | 说明 |
| --- | --- |
| 个性化访谈 | 收集目标类型、已知知识、各领域水平、时间预算、路线语言和资料语言偏好。 |
| AI/CS 技能树 | 内置数学、编程、ML/DL、LLM、RL、系统、论文阅读等前置知识结构。 |
| 多源资源发现 | 覆盖 GitHub、arXiv、OpenAlex、Semantic Scholar、Unpaywall、Papers with Code、YouTube、Bilibili、知乎、Hugging Face、Kaggle、MIT OCW、fast.ai、Google MLCC 等。 |
| 语言感知排序 | 支持 `zh-first`、`en-first`、`balanced`、`zh-only`、`en-only`。 |
| 论文深读路线 | 把目标论文作为第一资源，再补充前置知识、直觉视频、代码实现和复现检查点。 |
| 安全边界 | 拒绝盗版来源、绕登录、下载视频、长篇复制版权内容等不合规路径。 |
| Agent 友好输出 | 生成 Markdown 与 JSON，方便后续 agent 继续执行、复盘或扩展。 |

## 快速开始

```bash
python -m pip install -e .
python -m git4study.cli roadmap \
  --goal "从 Python 到掌握 Transformer" \
  --output-language zh-CN \
  --resource-language en-first \
  --offline
```

生成文件：

```text
git4study-output/
  learner_profile.json
  resource_index.json
  source_registry_snapshot.json
  roadmap.md
  roadmap.json
```

论文深读路线：

```bash
python -m git4study.cli paper \
  --url https://arxiv.org/abs/1706.03762 \
  --with-videos \
  --output-language bilingual \
  --resource-language en-first
```

查看可用资料源：

```bash
python -m git4study.cli discover-sources \
  --goal "理解 diffusion models" \
  --language zh-first
```

## 语言控制

路线语言和资料语言是两套独立设置。

| 参数 | 含义 |
| --- | --- |
| `--output-language zh-CN` | 用中文输出学习路线。 |
| `--output-language en` | 用英文输出学习路线。 |
| `--output-language bilingual` | 输出中英双语阶段名和检查点。 |
| `--resource-language zh-first` | 优先中文资料，但保留高质量英文资料。 |
| `--resource-language en-first` | 优先英文论文、课程、代码仓库，同时补充中文辅助材料。 |
| `--resource-language balanced` | 按质量混合中英文资料。 |
| `--resource-language zh-only` | 尽量只返回中文资料。 |
| `--resource-language en-only` | 尽量只返回英文资料。 |

## Agent 接入

### Codex / Claude Code Skills

安装或复制：

```text
skills/
  ai-cs-learning-path/SKILL.md
  paper-roadmap/SKILL.md
```

使用建议：

- `ai-cs-learning-path`：适合 broad topic、技能学习、项目复现、面试/考试准备；
- `paper-roadmap`：适合用户提供论文 URL、arXiv ID、DOI、PDF，并希望完全理解、推导、证明或复现。

### MCP 风格工具服务器

运行：

```bash
python -m git4study.mcp_server
```

每行发送一个 JSON 对象：

```json
{"tool":"discoverSources","arguments":{"goal":"理解 Transformer","resourceLanguagePreference":"zh-first"}}
```

可用工具：

- `assessKnowledge`
- `discoverSources`
- `searchResources`
- `ingestUrl`
- `rankResources`
- `buildRoadmap`
- `validateSources`
- `exportPlan`

### Cursor 和 VS Code

项目内置可改配置：

```text
.cursor/mcp.json
.cursor/rules/git4study.mdc
.vscode/mcp.json
```

## Source Registry

`source-registry.yaml` 声明每个平台的类型、语言覆盖、接入方式、认证需求、允许用途和质量信号。

当前覆盖：

- 代码学习：GitHub 仓库、awesome list、notebook、论文实现；
- 学术资料：arXiv、OpenAlex、Semantic Scholar、Unpaywall；
- 论文代码：Papers with Code；
- 视频平台：YouTube、Bilibili；
- 课程平台：MIT OCW、Google MLCC、fast.ai、DeepLearning.AI、学堂在线、中国大学 MOOC；
- 实践平台：Hugging Face、Kaggle；
- 中文社区：知乎，以及用户手动提供的链接。

对于商业平台、登录受限平台或 API 不稳定的平台，首版默认只做链接级推荐，不绕过平台限制。

## 架构

```text
用户目标
  -> 学习者访谈
  -> 语言策略
  -> 资料源发现
  -> 资源搜索 / URL 录入
  -> 排序与去重
  -> 学习路线生成
  -> Markdown + JSON 输出
```

核心模块：

```text
git4study/
  language.py         # 语言别名、双语 query、语言权重
  sources.py          # source registry 加载与策略过滤
  offline_catalog.py  # MVP 离线确定性资源目录
  ranking.py          # 评分、目标论文 boost、URL 规范化去重
  roadmap.py          # roadmap schema 与 Markdown 渲染
  mcp_tools.py        # agent 可调用工具函数
  mcp_server.py       # JSON-lines 工具服务器
  cli.py              # 命令行入口
```

## 安全策略

Git-4-Study Flow 只推荐、摘要和链接资料。它不会：

- 使用 Z-Lib、Sci-Hub、LibGen、Anna’s Archive 或其他盗版镜像；
- 绕过登录、付费墙或平台限制；
- 下载视频；
- 长篇复制受版权保护的内容；
- 把 README、字幕、评论、社区帖子里的文本当作可信 agent 指令。

所有外部资料都应被视为不可信来源，只用于摘要、引用和学习建议。

## 开发

```bash
python -m pip install -e .
pytest -q
```

当前测试覆盖语言偏好解析、双语 query 生成、registry policy、GitHub 风格排序信号、URL 去重、MCP 工具边界、安全校验、roadmap schema 和 CLI smoke tests。

## 路线图

- 接入 GitHub、YouTube、OpenAlex、Semantic Scholar、Hugging Face、Papers with Code 的官方 API adapter；
- 扩展 AI/CS 前置知识图谱；
- 增加进度追踪和间隔复习导出；
- 增加浏览器版路线预览；
- 打包正式 MCP SDK server。

## License

MIT. See [LICENSE](LICENSE).
