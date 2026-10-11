import type { Language } from "./messages";

const labels: Record<string, [string, string]> = {
  background: ["背景", "Background"], motivation: ["动机", "Motivation"], problem: ["问题", "Problem"],
  methodology: ["方法", "Method"], method: ["方法", "Method"], experiment: ["实验", "Experiment"],
  result: ["结果", "Result"], contribution: ["贡献", "Contribution"], limitation: ["局限", "Limitation"],
  target: ["论文", "Paper"], claim: ["论点", "Claim"], resource: ["资料", "Resource"], evidence: ["证据", "Evidence"],
  formula: ["公式", "Formula"], task: ["任务", "Task"], source: ["来源", "Source"],
  supports: ["支持", "Supports"], supported_by: ["来源支持", "Supported by"], motivates: ["促成", "Motivates"],
  addresses: ["回应问题", "Addresses"], solves: ["解决", "Solves"], evaluates: ["评估", "Evaluates"],
  implements: ["实现", "Implements"], implemented_by: ["实现于", "Implemented by"], tests: ["检验", "Tests"],
  reports: ["报告", "Reports"], measures: ["测量", "Measures"], constrains: ["限定", "Constrains"],
  contradicts: ["矛盾", "Contradicts"], depends_on: ["依赖", "Depends on"], requires: ["需要", "Requires"],
  related: ["相关", "Related"], related_to: ["相关", "Related to"], explains: ["解释", "Explains"],
  references: ["引用", "References"], cites: ["引用", "Cites"], derived_from: ["衍生自", "Derived from"],
  evidence_for: ["提供证据", "Evidence for"], configured_by: ["配置于", "Configured by"],
  explicit_reference: ["明确引用", "Explicit reference"], explicit: ["明确引用", "Explicit"],
  similarity: ["相似匹配", "Similarity"], similarity_match: ["相似匹配", "Similarity match"],
  heuristic: ["启发式匹配", "Heuristic"], lexical: ["词项匹配", "Lexical match"],
  local: ["本地分析", "Local analysis"], local_parser: ["本地解析", "Local parser"],
  parser: ["解析器", "Parser"], inferred: ["推测", "Inferred"], generated: ["生成", "Generated"],
  llm: ["模型生成", "Model generated"], model: ["模型生成", "Model"],
  manual: ["人工标注", "Manual"], user: ["用户标注", "User"], legacy: ["旧报告适配", "Legacy adapter"],
  paper_map: ["论文图谱", "Paper map"], paper_lens: ["论文精读", "Paper reading"],
  code: ["代码", "Code"], config: ["配置", "Configuration"], notebook: ["笔记本", "Notebook"],
  paper: ["论文", "Paper"], repository: ["代码仓库", "Repository"], book: ["书籍", "Book"], course: ["课程", "Course"],
  uses_config: ["使用配置", "Uses configuration"], evaluated_by: ["实验评估于", "Evaluated by"],
  bounded_by: ["边界限定", "Bounded by"],
  supplied: ["输入材料", "Supplied"], rule: ["规则匹配", "Rule match"], human: ["人工标注", "Human"],
  selected: ["路线已选", "Selected"], omitted: ["路线未选", "Omitted"], downloaded: ["已下载", "Downloaded"],
  copied: ["已复制", "Copied"], snapshotted: ["已快照", "Snapshotted"], failed: ["下载失败", "Failed"],
  "link-only": ["仅链接", "Link only"], unknown: ["未标注", "Unspecified"],
};
export function domainLabel(value: string, language: Language): string {
  return labels[value]?.[language === "en" ? 1 : 0] || (language === "en" ? value.replace(/_/g, " ") : "其他");
}
