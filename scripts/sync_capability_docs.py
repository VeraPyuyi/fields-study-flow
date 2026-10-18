"""Refresh capability descriptions; run from repository root."""
import json
from pathlib import Path

for file in [Path('source-registry.yaml'), Path('fields_study_flow/source-registry.yaml')]:
    data = json.loads(file.read_text(encoding='utf-8'))
    for source in data['sources']:
        source['notes'] = ('Implemented: public metadata adapter, bounded timeout, disk cache, no authentication. ' if source['id'] in {'arxiv', 'github'} else 'Link/catalog only: no live adapter implemented. ') + source.get('notes', '')
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

for name, replacements, extra in [
    ('README.md', {
        'mcp_server.py       # simple JSON-lines tool server': 'mcp_server.py       # SDK MCP stdio (--mcp), legacy JSONL default',
        '- Live official API adapters for GitHub, YouTube, OpenAlex, Semantic Scholar, Hugging Face, and Papers with Code.': '- Additional live API adapters for YouTube, OpenAlex, Semantic Scholar, Hugging Face, and Papers with Code.',
        '- Full MCP SDK packaging.': '- Wider MCP host GUI compatibility checks.',
        'Current source categories include:': 'Registered source categories (only arXiv/GitHub have live adapters):',
    }, '''
## Current capabilities and limits

`roadmap` remains offline by default. Add `--live --sources arxiv,github` to query public metadata APIs. MCP `searchResources` uses `filters={"offline": false}` for live queries; `type`, `language`, and `difficulty` filters apply to actual results. Offline catalog entries are suggestions, not live search matches. Other registered platforms are link/catalog only. Retrieval reports `offline`, `live`, `cache`, `mixed`, or `degraded` with reasons; network errors return no invented matches. API calls use a 5-second timeout, a 3-second minimum interval per service instance and a one-hour disk cache (`FIELDS_STUDY_FLOW_CACHE` overrides its directory). There are no paid APIs or authenticated fetches.

`ingestUrl` is URL-only by default. `fetchMetadata=true` requests public GitHub repository or arXiv metadata through the same service, refusing credentials and redirects. Unsupported hosts remain URL-only with an explicit degraded reason. GitHub resource language is the interface/metadata language (English); programming language is recorded separately and is not a natural-language classifier.

Standard MCP hosts must run `python -m fields_study_flow.mcp_server --mcp`. Both editor configurations use this command. The no-flag invocation and `--legacy-jsonl` retain the previous JSONL protocol, including the `git4study` alias. See [MCP transport](docs/MCP.md). The official SDK 2.x negotiates its supported protocol versions; local tests exercise initialize, eight tool schemas, calls, and errors. Editor GUI attachment remains an external check.

Ranking exposes relevance, trust, structure, difficulty, outcome and language components plus unmatched goal terms. A small bilingual alias map and domain levels improve explanations; this is lexical ranking, not semantic search. Thirty fixed review cases live in `tests/fixtures/ranking_cases.json`. Low lexical relevance is labeled supplemental. Prerequisites use a curated mathematics/programming/ML/DL/Transformer/LLM graph, skip explicitly known topics and appear before resource study. Numerical hours determine relative week ranges; unknown durations and infeasible target dates are explicit. These estimates are planning aids, not completion guarantees. Target papers anchor core study rather than the first foundation item.

Safety checks use parsed URL hosts/schemes and structured `metadata.access_policy` actions (`metadata`, `link`, `summarize`). Legacy notes retain compatibility checks for affirmative prohibited instructions; generated safety advice is not treated as an access operation.
'''),
    ('README.zh-CN.md', {
        'mcp_server.py       # JSON-lines 工具服务器': 'mcp_server.py       # SDK MCP stdio（--mcp）与旧 JSONL',
        '- 接入 GitHub、YouTube、OpenAlex、Semantic Scholar、Hugging Face、Papers with Code 的官方 API adapter；': '- 继续接入 YouTube、OpenAlex、Semantic Scholar、Hugging Face、Papers with Code adapter；',
        '- 打包正式 MCP SDK server。': '- 补充编辑器 GUI 的 MCP 连接验证。',
    }, '''
## 当前能力与限制

CLI `roadmap` 默认离线；`--live --sources arxiv,github` 显式调用公开元数据 API。MCP `searchResources` 传 `filters={"offline": false}` 启用实时检索，`type`、`language`、`difficulty` 会真正过滤资源。其他 registry 平台目前只有链接/目录能力。返回 `offline/live/cache/mixed/degraded` 和降级原因；失败不会伪造查询结果。默认超时 5 秒、同一服务实例请求至少间隔 3 秒、磁盘缓存 1 小时，缓存目录可由 `FIELDS_STUDY_FLOW_CACHE` 设置。不使用付费 API 或认证内容。

`ingestUrl` 默认只录入 URL；`fetchMetadata=true` 从公开 GitHub/arXiv API 获取元数据，拒绝凭据和重定向，其他来源明确降级。GitHub 的 `language=en` 表示元数据界面语言；编程语言另存 metadata，不保证仓库正文语言分类。

标准 MCP 启动命令为 `python -m fields_study_flow.mcp_server --mcp`，两份编辑器配置已同步。无参数启动和 `--legacy-jsonl` 保留旧 JSONL，`git4study` 入口兼容。协议版本由官方 SDK 2.x 协商，详见 [MCP 文档](docs/MCP.md)。本地 SDK 测试涵盖握手、8 工具 schema、调用和错误；编辑器 GUI 实际连接仍需外部验收。

排序输出相关性、可信度、结构、难度、成果偏好、语言等分项及缺失词项。小型中英别名表和领域等级避免全局降级；仍是词汇匹配，不是语义模型。30 条固定样例位于 `tests/fixtures/ranking_cases.json`。低相关性标为补充资料，不声称匹配。先修图覆盖数学/编程/ML/DL/Transformer/LLM，明确跳过已知主题；工时产生相对周排期，缺失时长标 unknown，期限不足会提示。目标论文放在核心阶段。工时是人工估算，不能保证实际完成时间。

合规校验使用解析后的 URL 主机/协议和 `metadata.access_policy` 的结构化动作（metadata/link/summarize）；旧记录的肯定违规指令保留兼容校验，不把生成的否定安全说明当成访问操作。
''')]:
    path = Path(name)
    text = path.read_text(encoding='utf-8')
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text + '\n' + extra, encoding='utf-8')
