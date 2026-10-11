# fields-study-flow 研究理解工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 已获准使用子智能体；任务结束后关闭子智能体。按下文里程碑提交可独立验证的改动，避免一次性替换整个项目。

**Goal:** 让研究者快速理解并接手 auto-research 产生的单篇论文及核心项目材料，能解释设计理由、定位实现和已有结果、识别证据缺口，并明确下一步如何继续研究。

**Architecture:** Python 负责解析、来源定位、证据关系、学习步骤与可选模型解释；React 工作台展示同一份结构化数据。保留静态离线 HTML、现有 CLI/MCP 和兼容导出，以一份共享研究上下文连接图谱、段落精读、实现证据与学习任务。

**Tech Stack:** 现有 Python/httpx/pypdf/nbformat、React 18/TypeScript/Vite/Tailwind/React Flow；新增 Lucide React 图标与 react-resizable-panels 分栏。继续使用 pytest、Vitest 和 Playwright 验证。

**计划日期:** 2026-10-10。**代码核对基线:** `5436f3e`，分支 `codex/paper-metadata-artifacts`。工作区已有 preset、CLI/MCP、文档和测试改动，实施时保留并纳入兼容检查。

**实施状态:** M1/M2/M3 工程功能已落地；M4 案例、文档与真人试用协议已准备，真人试用和同预算模型对照尚未执行。实际文件和安装包检查见[工程验收记录](../../evaluation/workbench-verification-2026-10-10.md)。发布状态以仓库远端提交为准。

---

## 1. 产品决策与范围

### 1.1 首批用户和价值

- 首批用户：需要理解自己或 Agent 生成的论文、代码和实验输出的研究者。
- 用户完成一次流程后，能够回答：为什么研究这个问题、方法如何工作、实现在哪里、结果在什么条件下成立、接下来应该检查或修改什么。
- 产品优势建设集中在四项：跨材料定位、围绕理解缺口安排步骤、可带走的研究学习包、随来源变化可重新核对的解释。
- 不把思维导图、摘要、聊天、测验或本地 HTML 单独宣传为独有能力；这些能力已可由通用模型产品提供。
- 学习效果和节省时间是待验证目标。资料数量、页面生成成功、引用存在和任务勾选，分别只表示相应操作完成。

### 1.2 已确定的体验

- B 工作台为主：左侧必要学习步骤，中间论文逻辑图或段落精读，右侧当前内容的解释与来源。
- A 大画布作为专注模式；C 的渐进理解方式用于段落精读和小例子。
- 接收论文及用户明确提供的 README、核心代码、配置和已有实验输出。第一版静态分析这些材料，不执行项目代码或重跑实验。
- 模型解释可选，只有用户显式启用后才请求模型；阅读导出的 HTML 不需要模型服务。
- 中文优先，同时支持英文；原文、标识符和外部资料标题保留原语言。首版不增加浏览器中的实时聊天服务。
- 页面语言优先服从显式的页面语言参数，其次服从 profile.output_language；auto 延续 prompt 的语言选择，无法判断时为中文。保留现有 bilingual 入口，双语解释在生成时准备，离线页面不假装能即时翻译。
- 单篇论文是本次交付范围。多篇论文和领域/课程现有入口保持可用，本次不扩展其新语义功能。

### 1.3 现有基础和已确认问题

| 项目 | 当前基础 | 本次处理 |
| --- | --- | --- |
| 展示架构 | React/Vite/React Flow 已存在，Python 有离线导出和 fallback | 直接改造现有架构，不再次建立另一套前端 |
| 论文解释 | `paper_map.py` 存在符号规划专用固定解释；精读有重复模板补尾句 | 改为来源约束的通用解释，缺少材料时诚实降级 |
| 画布状态 | 分支切换会重建节点，React Flow 的 key 随视图变化 | 维护稳定节点状态，解决拖拽位置和视图重置 |
| 信息层级 | 页面头部、下载统计和多组就绪指标占据较多空间 | 第一屏优先呈现论文逻辑和当前学习动作 |
| 项目材料 | 能摄取代码、Notebook 等文本，但缺少明确实现/结果关系 | 新增有定位的材料关系；推测关系保留待核对状态 |
| 掌握状态 | 已有任务、勾选和 worksheet | 区分自我记录、提供回答和经核对的回答 |
| 交付文件 | 源码、打包前端和用户目录中的旧报告可能不同步 | 验收最终导出的文件和安装包，不只检查源码 |

## 2. 用户流程与界面规格

### 2.1 一次完整流程

1. 输入论文，选择“看懂 / 汇报 / 接手修改”，声明已知背景；需要时附上项目目录和结果文件。
2. 打开主报告，首先看到短标题、论文核心逻辑和一个可立即开始的学习步骤。
3. 点击方法或贡献，右侧解释其含义、一个可用的小例子、前后关系，以及原文和项目材料定位。
4. 遇到不懂的概念，展开必要背景；需要核对实现时，在同一上下文内查看代码和配置。
5. 完成针对当前目标的理解问题，留下自己的解释和来源；系统据此推荐下一步。
6. 导出笔记、回答和待检查事项。再次生成时，发生变化的来源对应内容提示重新核对。

### 2.2 三个入口使用同一套工作台

- `paper_map.html`：单篇论文主入口。主链为背景、动机、问题、方法、实验、结果/贡献、局限；资料和任务作为按需展开分支。
- `paper_lens.html`：段落精读入口。正文按完整段落正常排版，当前段落用轻量边线标记；说明在右侧，不把整段文字渲染成粗体按钮。
- `roadmap.html`：学习步骤、资料库和下载管理；复用同一顶部导航与当前上下文。
- `index.html`：轻量入口，突出“开始理解论文”，保留无脚本可读内容；不再叠加一套重复的完整仪表盘。
- 旧文件名和段落详情锚点保持有效。链接只指向本次实际生成的文件。

### 2.3 视觉与尺寸

- 基础背景 `#F7F8FA`，面板白色，正文 `#24272D`，次级文字 `#626971`，边框 `#DDE2E7`。操作强调色用青绿，方法关联用蓝色，待核对状态用琥珀色；状态同时有文字，不单靠颜色。
- 字体沿用中文优先栈。正文 16px、行高 1.75；紧凑面板 14px、行高 1.6；主标题 20px。字间距为 0，不用 viewport 单位缩放字体。
- 顶部紧凑导航与上下文栏合计约 88px。桌面工作台占用剩余视口高度，各栏独立滚动，主图不被大段说明挤到折叠线以下。
- 1280px 及以上默认左栏 224px、右栏 360px，中心自适应；左右栏可拖动分隔、折叠和恢复。中等屏幕默认收起辅助栏，小屏使用图谱预览、节点列表和详情抽屉。
- 页面区块采用分栏和分隔线。节点、独立资源项与弹窗圆角不超过 8px，不做卡片套卡片。
- 图标按钮使用 Lucide，并提供中文或英文的可访问名称和悬浮提示。常规正文不放交互操作说明。

### 2.4 图谱和阅读交互

- 主图初始只显示论文节点和核心逻辑节点，采用紧凑的三列折返布局；在受测桌面视口下完整主链可见、标签有效字号至少 13px。核心节点只展示简短名称和状态，完整解释在右侧。
- 名称过长时自然换行并增加节点高度，由测量后的尺寸排布；不通过裁掉正文或缩小整图来容纳长解释。
- 点击节点高亮相关路径；右侧和左侧步骤同步选择。选择段落时同步对应图谱节点与来源。
- 每个主节点独立控制分支展开；折叠仅改变可见状态，不删除节点或用户拖动位置。折叠当前选中分支时选回其父节点。
- 初次打开且没有保存视图时自动适应主链；拖拽、选择、切换分支和拖动分隔栏不触发整图重新缩放。显式“适应窗口”和“重置布局”才重新排布或取景。
- 待机保持静止；悬停改变边框与背景；选中突出关联路径；拖拽显示抓取光标和轮廓。移除拖拽旋转、节点缩放和持续流动的连线动画。
- 过渡时间 120–180ms，只作用于颜色、透明度和面板展开；遵守 `prefers-reduced-motion`。图形数据、组件函数和事件处理器保持稳定引用。
- 节点位置、分栏、展开状态和学习记录分别保存；localStorage 失败时保留会话内操作，并提供可导出的学习记录。
- 资料库默认全部可见，任务过滤由用户主动开启并明确显示。已落地资料优先打开相对本地链接，原始链接作为次级入口。
- 沿用 `bundle_scope=all` 的完整打包默认值；图中收起资料和路线精简均不删除候选资料，用户仍可显式选择 selected 减少下载。

## 3. 数据、内容与接口

### 3.1 共享研究上下文

新增 `roadmap.json.research_context`，旧字段继续输出。图谱、段落解释和任务引用同一来源与论点，不再分别生成相互不一致的说明。

```ts
type ResearchContext = {
  schema_version: 1;
  bundle_id: string;
  snapshot_id: string;
  sources: ResearchSource[];
  anchors: SourceAnchor[];
  claims: ResearchClaim[];
  relations: ResearchRelation[];
  learning_steps: LearningStep[];
};
type ResearchSource = {
  id: string;
  kind: "paper" | "readme" | "code" | "config" | "result" | "notebook";
  title: string;
  fingerprint: string;
  relative_path?: string;
  local_href?: string;
  url?: string;
};
type SourceAnchor = {
  id: string;
  source_id: string;
  locator: { page?: number; section?: string; symbol?: string;
    line_start?: number; line_end?: number; cell_id?: string;
    json_pointer?: string; row?: number; column?: string };
  snippet: string;
  locator_status: "valid" | "missing" | "stale";
};
type ResearchClaim = {
  id: string;
  kind: "background" | "motivation" | "problem" | "methodology" |
    "experiment" | "result" | "contribution" | "limitation";
  statement: string;
  anchor_ids: string[];
  evidence_status: "located" | "partial" | "missing" | "stale";
};
type ResearchRelation = {
  id: string;
  from: string;
  to: string;
  kind: "motivates" | "addresses" | "implements" | "uses_config" |
    "evaluated_by" | "supports" | "bounded_by";
  anchor_ids: string[];
  origin: "supplied" | "rule" | "model" | "human";
  review_status: "unreviewed" | "accepted" | "rejected";
};
type LearningStep = {
  id: string;
  title: string;
  claim_ids: string[];
  prerequisite_ids: string[];
  anchor_ids: string[];
  task_ids: string[];
  estimated_minutes: number | null;
  reason: string;
  status: "available" | "needs_material";
};
```

- 来源指纹记录内容版本；生成目录中的 bundle 身份在同一目标重生成时保持，snapshot 随来源或关键生成配置变化。来源和节点有稳定 ID，不以显示标题作为唯一标识。
- 本地私有索引持有真实文件路径；公开模型只保留相对定位与短摘录。来源目录迁移不应使包内相对链接失效。
- `locator_status=valid` 只说明定位有效；`evidence_status=located` 只说明已找到所引材料。两者均不表示论点正确或用户已经掌握。
- 模型和规则生成的关系默认待核对。用户或上游给出的关联也保留其来源，不能因上传了 manifest 就自动认定为正确。
- 旧报告没有 `research_context` 时，适配已有来源、段落和任务；不能定位的关联标记缺失，不编造代码行号或结果文件。

### 3.2 项目材料与解释生成

- 第一版项目适配：README/Markdown、Python AST 函数/类、Notebook 单元格、JSON/YAML 配置、CSV/JSON 已有结果。其他代码先作为可搜索文本，不假称具备符号级理解。
- 沿用显式本地路径边界；跳过已有规则排除的目录、二进制和越界链接。扫描达到数量或大小限制时记录覆盖范围，在材料面板显示未分析项。
- 对代码、配置、结果的自动匹配先生成候选关系。优先明确的文件引用、符号引用和运行标识，关键词相似度不能直接产生“已证明”关系。
- PDF 段落保留页码和章节；过滤页眉页脚、目录、关键词串，图注与公式块单独标识，避免把碎片伪装为完整段落。
- 本地模式给出原文摘要、术语定位和有依据的结构说明。中文释义不足时明确显示原文与待补内容，不把某篇论文的解释套到另一篇。
- 模型模式为每段生成含义、逻辑作用、必要的方法解释，并允许为空；只有确有帮助时添加小例子。概念类比必须标明是教学例子，不能伪装成论文结果。
- 模型回答必须引用已提供的 anchor ID。检查 ID 存在、摘录匹配、定位有效；不接受模型发明的文件、来源或实验数值。通过定位检查仍保留解释待核对状态。
- 模型只在生成阶段工作；HTML 阅读和普通重导出不再次调用模型。缓存键包含来源指纹、语言、模型、解释规则版本。
- 整节集中推荐阅读资料，不在每个段落重复输出相同书单。不用追加一句原文来掩盖相同解释模板。

### 3.3 学习目标和进度

- 新增学习目标 `understand | present | extend`，默认 `understand`。现有 `fast-presentation` preset 映射到 `present`，显式参数优先；其他 preset 保留原行为。
- 学习目标首先调整展示顺序和必要步骤，不能删除用户目标或既有接口明确要求的推导、复现和批判任务；保留原有正式任务及其证据要求。
- `understand` 的产物是用自己的话解释问题、方法和边界；`present` 增加来源明确的汇报提纲与追问；`extend` 增加实现入口、关键配置、已有结果与一个后续修改假设。
- 学习依赖单独来自必要概念和任务条件，不能把论文因果边直接当成先修依赖。
- 复用已知主题和水平信息；可选做少量诊断问题。依据未覆盖目标、必要先修知识和估计耗时排序，采用确定性启发式，不宣传全局最短路径。
- 材料缺失时保留相应学习步骤并标记待补材料。生成的实验骨架不算已有实现或已完成复现。
- 学习记录分为未开始、学习中、已填写回答、自我核对、已复核；自我核对与模型反馈都有明确来源。初版不自动授予“完全掌握”。
- `study_state.json` 可导入导出，记录回答、笔记、步骤 ID、来源指纹和版本。旧来源变化后将受影响回答标为待重新核对；其他答案保留。公开 `roadmap.json` 不默认包含个人回答。

### 3.4 公共接口与兼容

| 接口 | 新增或调整 | 默认与兼容 |
| --- | --- | --- |
| CLI `paper` / `roadmap` | `--learning-outcome understand\|present\|extend` | 默认 understand；已有 preset 和显式覆盖继续生效 |
| CLI `paper` | 补齐与 roadmap 相同的 `--known-topic`、`--level`、`--offline` | 明确用户背景；offline 关闭生成时的全部网络请求 |
| CLI 生成入口 | `--explanation-provider local\|auto\|llm` | auto 无显式启用配置时使用 local；保留旧 map provider 参数作为兼容输入，新参数显式给出时优先 |
| 项目导入 | 继续使用 `--local-resource` | 本次不新增多套相似的项目导入命令 |
| MCP `buildRoadmap` | 可选 `learningOutcome`、`explanationProvider`、`researchContext` | 旧调用有效；传入 context 必须验证引用与版本 |
| MCP `exportPlan` / CLI `export` | 保留 research_context，统一调用导出管线 | 重导出默认不联网、不重复调用解释模型 |
| JSON | 可选 research_context、profile.learning_outcome | 不删除 paper_map/paper_lens/knowledge_graph/mastery_graph |
| HTML | 继续输出三个已有主文件与 index | 本地 file 协议直接打开；脚本失败时仍有可读内容 |

- HTTP 模型适配第一版支持用户配置的 OpenAI-compatible Chat Completions 端点，使用已有 httpx；不内置付费服务或默认模型。端点、模型名与显式启用状态从用户配置读取，密钥只从环境或私有配置读取。
- 明确选择 llm 但配置缺失时，在生成前报出可操作的配置错误；网络失败时导出本地模式结果并记录降级。auto 不会因为发现任意 API key 就自动上传材料。
- `--no-live-search` 继续控制资源发现；要关闭包括模型在内的所有网络活动使用 `--offline`。offline 优先于 provider 配置。
- 用户启用外部解释时只发送本次显式输入材料的必要片段。模型响应作为不可信数据处理；密钥、绝对路径和响应中的脚本不进入公开报告。

## 4. 实施任务和交付顺序

下列路径均相对于仓库根目录。实现按每项中的“复现/约束测试 → 修改 → 定向验证”推进。测试关注实际输入输出与用户行为，不只检查 CSS 类名或函数是否存在。

### M1：可信内容与可用工作台

#### Task 1：建立跨论文回归用例，修复模板化解释

**文件:** 修改 `fields_study_flow/paper_map.py`、`fields_study_flow/paper_lens.py`；测试 `tests/test_paper_map.py`、`tests/test_paper_lens.py`；新增 `tests/fixtures/research_workbench/`。

- [x] 加入规划、Transformer、扩散、无代码的实验论文和材料不全五类精简 fixture，保留各自可核对的来源片段。
- [x] 先加入能复现问题的测试：不含规划内容的目标不能生成 PDDL/VAL/PlanBench 解释；两个不同方法段落不能只得到同一个固定解释加尾句。
- [x] 移除通用分支中的特定论文结论；将可保留的领域词汇表限定为原文实际命中后的术语说明。
- [x] 修复段落提取、重复标题、关键词串误识别、无依据置信度与不必要省略号。保留完整文本，通过信息层级控制密度。
- [x] 运行 `python -m pytest -q tests/test_paper_map.py tests/test_paper_lens.py`，检查五类内容均有来源或明确缺口。

#### Task 2：重建共享工作台外壳与双语显示

**文件:** 修改 `frontend/src/shared.tsx`、`frontend/src/styles.css`、`frontend/src/App.tsx`、`frontend/src/types.ts`、`frontend/package.json` 和 lockfile；新增 `frontend/src/workbench/WorkbenchLayout.tsx`、`frontend/src/workbench/messages.ts`、`frontend/src/workbench/useStudyState.ts`。

- [x] 提取共用布局、语言文案与安全存储 hook，先让旧 report 数据经过适配也能进入工作台。
- [x] 接入 Lucide 和 react-resizable-panels 的 `Group/Panel/Separator`，按其已锁定版本的 API 使用显式尺寸单位；分隔栏支持键盘调整。
- [x] 按第 2 节落实字体、颜色、分栏、短标题和三入口导航。把下载统计、书单和汇报稿移入按需展开区域。
- [x] 存储读取、写入失败与旧记录字段缺失均不阻断渲染。用户生成的笔记按文本显示。
- [x] 定向组件测试覆盖中英文文案、侧栏折叠、恢复、存储不可用和旧报告；不通过测试要求把已删除的冗余面板重新加回来。

#### Task 3：稳定 Paper Map 和段落精读的联动

**文件:** 修改 `frontend/src/PaperMapApp.tsx`、`frontend/src/PaperLensApp.tsx`、`frontend/src/data.ts`；新增 `frontend/src/workbench/PaperNode.tsx`、`frontend/src/workbench/ContextPanel.tsx`、`frontend/src/workbench/mapState.ts`、`frontend/src/workbench/Workbench.test.tsx`。

- [x] 使用自定义节点，节点数组由稳定 ID 管理。去掉由分支或视口改变 React Flow key 的行为，避免初始化 effect 覆盖用户位置。
- [x] 将分支显隐、视口、拖动位置和选择状态分开；按 source/target ID 计算邻居和路径，高亮时不重新创建布局。
- [x] 落实紧凑初始布局、分支展开、适应窗口、重置、拖拽、侧栏联动；在拖拽结束和视口移动结束时保存状态。
- [x] 段落正文恢复可选中阅读文本，用单独按钮或段落标记切换解释；点击与旧 hash 链接均能选择对应段落并定位。
- [x] 检验长中文、长英文词、公式、长资料名，以及 20 次连续切换分支后节点仍存在、位置不重置、连线不悬空。

**M1 交付:** 五类输入都能生成诚实、可读的内容；实际离线报告中图谱可读、可拖动、分支稳定，段落精读和侧栏有明确联动。此阶段不宣称已经完成项目级证据映射。

### M2：建立可定位的论文与项目关系

#### Task 4：来源锚点、材料关系和变更检查

**文件:** 新增 `fields_study_flow/research_context.py`、`fields_study_flow/project_evidence.py`、`tests/test_research_context.py`、`tests/test_project_evidence.py`；修改 `fields_study_flow/local_resources.py`、`fields_study_flow/resource_bundle.py`、`fields_study_flow/roadmap.py`。

- [x] 按第 3.1 节实现有版本的共享数据结构与校验器；先测试不存在的引用、重复标题、失效锚点和旧数据适配。
- [x] 提取 PDF 页/段、Python 符号/行、Notebook 单元格、配置键和表格值定位。解析错误局限于对应材料，仍导出其余可用内容。
- [x] 为明确引用与相似匹配生成带 origin 的关系；无证据时只生成待核对候选。测试标题相似但方法不同的代码不会直接被认定为实现。
- [x] 记录来源指纹；只对受变化影响的定位和回答提示复核。建立私有路径到公开相对链接的映射。
- [x] 用一个带 README、Python、配置、JSON/CSV 结果的自有小项目 fixture 验证完整链路；清楚标记为演示材料，不声称复现真实论文。
- [x] 在右侧加入“原文 / 实现 / 实验材料”上下文视图。代码锚点通过内嵌只读片段显示行号并提供本地原文件入口，不依赖操作系统支持行号 URL。

#### Task 5：统一生成和导出，交付可移动的资料包

**文件:** 新增 `fields_study_flow/report_export.py`、`tests/test_report_export.py`；修改 `fields_study_flow/roadmap.py`、`fields_study_flow/mcp_tools.py`、`fields_study_flow/frontend_report.py`、`fields_study_flow/cli.py`。

- [x] 将 CLI 与 MCP 重复的报告写出逻辑合并到共享导出器；语言/深度设置和新研究上下文不在导出时被默认值覆盖。
- [x] 本地解析和证据定位发生在统一脱敏前；资料包创建后只重绑定 local_href，不重复生成解释。
- [x] 所有页面使用同一份公开快照。已下载、复制和快照资料优先本地链接；同名资源按稳定 ID 和 URL 匹配。
- [x] 保留 JSON/MD/SVG、精读 PDF/TeX、已有模板导出与旧字段。无前端构建产物时保留 Python fallback；静态 fallback 也使用新的通用内容。
- [x] 验证整个输出目录搬到不同位置后本地链接仍工作；跨资料包目录的相对引用在 README 明确列出需要一起移动的目录。
- [x] 验证 `file://`、禁网、禁 localStorage、脚本失败、旧报告重导出与恶意 `</script>` 文本，确认可读、无路径泄露且无意外脚本执行。

**M2 交付:** 点击一项研究方法或结果，可以定位论文原文和可用的项目材料；缺少实现、配置或结果时界面明确说明。资料包能离线打开并随目录一起交接。

### M3：解释增强与针对性学习

#### Task 6：受来源约束的可选解释 provider

**文件:** 新增 `fields_study_flow/explanations.py`、`fields_study_flow/explanation_provider.py`、`tests/test_explanations.py`、`tests/test_explanation_provider.py`；修改 `fields_study_flow/paper_map.py`、`fields_study_flow/paper_lens.py`、`fields_study_flow/cli.py`、`fields_study_flow/mcp_tools.py`。

- [x] 定义统一 provider 输入为目标、语言、当前段落和允许引用的 anchors，输出为结构化解释、例子和引用。图谱与精读从同一结果投影。
- [x] 实现本地模式与配置显式启用的 HTTP 适配器；模型名和端点均由用户提供。HTTP 请求有超时，重试有上限，外部异常不把密钥或完整私有响应写入日志。
- [x] 用 mock endpoint 验证正确解释、未知 anchor、虚构数值、无效 JSON、超时与限流；未知或无法核对的内容不能进入已定位解释。
- [x] 对源文确有数值的解释只保留能回指原文的数值；无法自动判定其科学含义时保持待核对。没有模型时仍能使用 M1/M2 全部阅读与定位功能。
- [x] 验证缓存命中、来源变化失效、显式 offline 零网络请求，以及重导出不再次计费。

#### Task 7：围绕目标生成必要步骤和接手任务

**文件:** 新增 `fields_study_flow/learning_path.py`、`tests/test_learning_path.py`；修改 `fields_study_flow/models.py`、`fields_study_flow/roadmap.py`、`frontend/src/RoadmapApp.tsx`、`frontend/src/workbench/useStudyState.ts`；新增 `frontend/src/workbench/LearningRail.tsx`、`frontend/src/workbench/StudyState.test.tsx`。

- [x] 实现 understand/present/extend 目标与 preset 映射，复用 known_topics/levels；已掌握概念不重复占用必要步骤。
- [x] 用有向无环的先修关系生成学习顺序。遇到冲突或循环时保留可读的建议顺序并暴露关系待核对，不进入死循环。
- [x] 必要材料优先选能覆盖当前问题的原文和已有项目证据；耗时未知时显示待估计，不当作零成本参与最短排序。
- [x] 每个步骤绑定可回答的具体问题和检查要点；汇报目标绑定出处，接手目标绑定实现入口、可变配置和预期观察，不自动运行实验。
- [x] 实现学习记录导入导出、个人回答与公开报告分离；用户自行跳过的步骤保留理由和返回入口。
- [x] 使用跨领域 fixture 验证：背景熟悉用户的必要步骤减少；缺失材料不会被掩盖；勾选和模型评分不会自动把状态改成已掌握。

**M3 交付:** 用户能围绕自己的目标获得必要学习步骤与可携带的笔记、回答和待检查事项；可选模型解释有真实来源定位，内容质量与来源覆盖分开呈现。

### M4：验证价值并形成开源入口

#### Task 8：真实示例、比较评估和发布文档

**文件:** 修改 `README.md`、`README.zh-CN.md`、`docs/COMPETITIVE_NOTES.md`、`docs/MARKET_POSITIONING_2026.md`、`fields_study_flow/visual_audit.py`、`skills/paper-roadmap/SKILL.md`；新增 `docs/evaluation/research-understanding-protocol.md`、`examples/research-workbench/`。

- [x] 制作三个可直接打开的公开案例：论文为主、论文加实现、材料有缺口；覆盖规划、Transformer 和扩散等不同主题。第三方代码标明与论文的实际关系，演示结果与真实实验结果分开。
- [x] 示例只使用可再分发内容或许可允许的短摘录，提供原始来源和版本。示例没有的真实项目材料明确留空，不生成伪实验来凑全链路。
- [x] 更新 Skill/MCP 使用路径，使 auto-research 完成后能把用户指定目录交给本项目；默认入口只需目标和材料，高级参数渐进展示。
- [ ] 编写一次小规模真实用户试用协议，招募目标用户后执行；招募前不填写假结果。自动化测试与用户效果评估分别报告。
- [x] 开源文档说明一个完整工作流、支持材料、可选模型费用边界和目前限制，附实际导出页面截图；维护可认领的解析适配、解释修正、案例与界面问题。
- [ ] 用同一套输入与预算比较“直接使用模型/Agent”与“相同模型加本项目”，公开失败案例和实际结果，不只展示成功截图。

## 5. 验收与交付门槛

### 5.1 内容和行为验收

| 场景 | 必须观察到的行为 |
| --- | --- |
| 不同领域论文 | 解释与本论文内容相符，不混入规划领域固定结论 |
| 只有摘要或缺页 PDF | 显示材料覆盖范围；缺失方法或实验不编造 |
| 论文加代码加结果 | 来源锚点可定位；候选关系与人工确认关系区分 |
| 没有代码或结果 | 图谱和理解步骤仍可用；接手步骤明确列出缺口 |
| 原文或代码变更 | 相关锚点和回答提示复核，未受影响记录保留 |
| 未配置或关闭模型 | 离线功能完整可用，无外部解释请求 |
| 中英长文本和公式 | 正文、节点、按钮不越界，不靠堆叠省略号隐藏解释 |
| 分支展开和拖拽 | 连续操作无消失节点、位置重置、悬空边或突然缩放 |
| 三个报告互跳 | 目标文件、段落锚点、当前选择和本地资料入口真实可达 |
| 存储不可用或页面出错 | 可继续阅读；临时进度和静态内容可用 |

### 5.2 工程验证

- 后端：对受影响模块运行定向测试，集成完成后运行 `python -m pytest -q`。不引用旧轮次测试数量作为本轮通过证据。
- 前端：在 `frontend/` 运行 `npm ci`、`npm test`、`npm run build`；构建后校验打包到 Python 的资产与本次源码一致。
- 浏览器：实际打开导出文件，覆盖 1440×900、1280×800、390×844、768×1024；记录页面错误、外部请求、溢出、节点位置和真实点击结果。
- 性能：固定 Chromium/设备条件记录首次可操作时间与拖动轨迹；100 节点合成压力案例在拖动时不得触发完整图谱重建或连续长任务。观察结果写入验证记录，不虚构通用帧率承诺。
- 交付：从新构建的 wheel 在临时目录安装并生成报告；断网打开三页，核对本地链接、无脚本阅读内容和中文排版。运行 `git diff --check`。
- 更新用户已有 Teaching LLMs to Plan 报告时保留资料包和个人记录，重新生成主 HTML 后再验收；不能只展示开发服务器页面。

### 5.3 用户效果验证

- 先做 8–12 名目标用户的小规模探索性试用，记录背景和已有知识；结果用于发现可用性问题，不作为总体有效性的统计证明。
- 使用等难度不同材料，交叉安排工具顺序，避免用户在第二次学习同一篇论文时因记忆而获益。
- 同模型比较时保持模型版本、可用资料和预算一致；原生 GPT/Claude/Agent 产品比较单独报告其工具配置，不与同模型实验混为一组。
- 基线提供清楚的任务说明和合理的工具访问，不故意使用弱提示词；学习计时与生成等待时间分别记录，也报告端到端总耗时。
- 核心指标：正确独立解释所需时间、出处定位正确率、发现不支持结论的能力、定位修改入口的成功率；同时记录生成时间、交互步骤、模型成本和放弃原因。
- 由熟悉材料的人依据预先固定的评分要点评阅，尽量不知道参与者使用了哪种工具。参与者未完成也纳入结果。
- 初始发布门槛是完整流程可用且没有未解决的阻断问题；只有实测支持时才宣传速度或效果提升，避免人为设定百分比后反推宣传文案。

## 6. 实施组织与完成定义

- 顺序：M1 先交付用户可见改善；M2 建立核心差异；M3 增强解释和个性化；M4 验证价值与完善开源入口。
- 可并行边界：Task 1 与 Task 2；Task 4 的解析工作与已稳定的 UI 实现；Task 6 与 Task 7 在共享数据合约确定后可并行。同一大文件由一个实现者负责，其他人通过接口交接。
- 每个里程碑提供实际可打开的报告、定向测试结果、桌面/移动截图和剩余限制；独立审查重点覆盖真实功能和内容，不能只做静态代码检查。
- 提交只包含本轮相关改动；现有未提交 preset 改动先检查并保留，不用清理工作区的方式消除。公开推送和发布在实施交付阶段按用户授权处理。
- 本次计划完成的标志：范围、数据和接口、界面行为、实施任务和效果验证方法已写清；不把拟定计划算成功能完成。

## 7. 官方参考与定位边界

- [ChatGPT Study Mode](https://help.openai.com/en/articles/11780217-using-study-mode-in-chatgpt)：已有引导学习、分层解释和理解检查，因此这些单项功能不作为独占卖点。
- [Claude Artifacts](https://support.claude.com/en/articles/17153992-what-are-artifacts-and-how-do-i-use-them)：已有交互工具和图表创建，离线页面美化本身不能证明产品优势。
- [NotebookLM 学习卡片和测验](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-app-quizzes-flashcards/)：来源驱动的学习辅助已存在，本项目应以研究理解和接手完整流程接受比较。
- [React Flow 性能建议](https://reactflow.dev/learn/advanced-use/performance)：参考稳定组件引用与受控更新的做法，具体性能以本项目浏览器测量为准。
- [react-resizable-panels](https://github.com/bvaughn/react-resizable-panels)：复用可访问的可调整分栏；锁定安装版本并核对 API，不混用旧版命名。
- [Lucide React](https://lucide.dev/guide/react)：使用本地打包的图标组件，不依赖在线图标或字体服务。

这些参考支持功能事实与实现选择，不证明本项目已经具备相同能力或更好的学习效果。
