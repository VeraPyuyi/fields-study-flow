import { useEffect, useMemo, useState } from "react";
import { Header, ResourceButton } from "./shared";
import type { Evidence, ResourceLink, Roadmap, StudyTask } from "./types";

const SUCCESSFUL_RESOURCE_STATUSES = new Set(["downloaded", "copied", "snapshotted", "generated"]);
type ResourceFilterId = "all" | "local" | "materialized" | "failed" | "link-only" | "paper" | "repository" | "book-course";

const RESOURCE_FILTERS: Array<{ id: ResourceFilterId; label: string }> = [
  { id: "all", label: "全部资料" },
  { id: "local", label: "本地可打开" },
  { id: "materialized", label: "已落地" },
  { id: "failed", label: "下载失败" },
  { id: "link-only", label: "仅链接" },
  { id: "paper", label: "论文" },
  { id: "repository", label: "代码仓库" },
  { id: "book-course", label: "书籍/课程" },
];

const TASK_TYPE_LABELS: Record<string, string> = {
  explain: "解释",
  derive: "推导",
  reproduce: "复现",
  critique: "批判",
};

const MASTERY_GATE_ORDER = [
  {
    type: "explain",
    label: "解释",
    readyAction: "已经绑定资料，可以直接做无笔记讲解。",
    needsAction: "补一条能支撑讲解的论文段落或资料来源。",
    missingAction: "先补一个解释任务，让路线能检验是否听得懂。",
  },
  {
    type: "derive",
    label: "推导",
    readyAction: "已经绑定资料，可以整理关键公式或机制推导。",
    needsAction: "补一条公式、方法或机制证据后再验收。",
    missingAction: "补一个推导任务，避免只会复述不会拆解方法。",
  },
  {
    type: "reproduce",
    label: "复现",
    readyAction: "已经绑定资料，可以进入最小实验或代码验证。",
    needsAction: "补一个 notebook、代码仓库或实验说明作为证据。",
    missingAction: "补一个复现任务，让掌握结果可运行、可检查。",
  },
  {
    type: "critique",
    label: "批判",
    readyAction: "已经绑定资料，可以说明适用边界和局限。",
    needsAction: "补一条局限、失败案例或对比资料作为证据。",
    missingAction: "补一个批判任务，避免报告只讲优点不讲边界。",
  },
] as const;

type MasteryGateStatus = "ready" | "needs_evidence" | "missing";

function numeric(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function countByStatus(resources: ResourceLink[], status: string) {
  return resources.filter((resource) => resource.status === status).length;
}

function buildMasteryWorksheet(roadmap: Roadmap, tasks: StudyTask[], completedTaskIds: Set<string>) {
  const title = roadmap.title || roadmap.profile?.goal || "fields-study-flow 学习路线";
  const completed = tasks.filter((task, index) => completedTaskIds.has(taskId(task, index))).length;
  const lines = [
    `# ${title} 掌握证据清单`,
    "",
    `- 学习目标：${roadmap.profile?.goal || title}`,
    `- 当前进度：${completed}/${tasks.length}`,
    "- 使用方式：每完成一项任务，就在“我的证据”下面填写讲解、推导、实验输出、截图、Notebook 链接或批判笔记。",
    "",
  ];
  if (!tasks.length) {
    lines.push("暂无验收任务。请重新生成包含 explain / derive / reproduce / critique 的学习路线。", "");
    return lines.join("\n");
  }
  tasks.forEach((task, index) => {
    const id = taskId(task, index);
    const status = completedTaskIds.has(id) ? "已完成" : "待完成";
    const type = TASK_TYPE_LABELS[task.type || ""] || task.type || "任务";
    const resources = (task.resource_titles ?? []).length ? (task.resource_titles ?? []).join(" / ") : "未绑定资料";
    lines.push(
      `## ${index + 1}. ${task.title || `验收任务 ${index + 1}`}`,
      "",
      `- 类型：${type}`,
      `- 状态：${status}`,
      `- 预计耗时：${task.estimated_minutes ? `${task.estimated_minutes} 分钟` : "待估计"}`,
      `- 相关资料：${resources}`,
      `- 验收标准：${task.acceptance || "能解释给别人听，并能回到论文证据。"}`,
      `- 任务证据要求：${task.evidence || "完成后留下可复查的学习证据。"}`,
      "",
      "我的证据：",
      "- ",
      "",
    );
  });
  return lines.join("\n");
}

function summaryCount(summary: Record<string, number | string>, resources: ResourceLink[], key: string) {
  const fromSummary = numeric(summary[key]);
  return fromSummary || countByStatus(resources, key);
}

function resourceStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    downloaded: "已下载",
    copied: "已复制",
    snapshotted: "已快照",
    generated: "生成模板",
    failed: "下载失败",
    "link-only": "仅链接",
  };
  return labels[status || ""] || status || "待处理";
}

function resourceSearchText(resource: ResourceLink, roadmap?: Roadmap) {
  const purpose = resourcePurpose(resource);
  const strength = resourceStrength(resource);
  const provenance = resourceProvenance(resource);
  const coverage = roadmap ? resourceCoverage(resource, roadmap) : { items: [], detail: "" };
  return [
    resource.title,
    resource.label,
    resource.source,
    resource.type,
    resource.language,
    resource.status,
    resource.url,
    resource.href,
    resource.local_href,
    ...(resource.concepts ?? []),
    ...(resource.learning_key_points ?? []),
    ...(resource.focus_areas ?? []),
    purpose.label,
    purpose.reason,
    strength.label,
    strength.evidenceLabel,
    provenance.label,
    provenance.detail,
    ...(coverage.items ?? []),
    coverage.detail,
    resourceStrengthReason(resource),
    strongestEvidenceSnippet(resource),
    resource.why_recommended,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function normalizeResourceKey(value?: string) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/^local:\/\//, "")
    .replace(/[?#].*$/, "")
    .replace(/\s+/g, " ");
}

function resourceKeys(resource: ResourceLink) {
  return [
    resource.url,
    resource.href,
    resource.local_href,
    resource.title,
    resource.label,
  ]
    .map(normalizeResourceKey)
    .filter(Boolean);
}

function mergeMetadata(primary?: Record<string, unknown>, secondary?: Record<string, unknown>) {
  const base = secondary && typeof secondary === "object" ? secondary : {};
  const override = primary && typeof primary === "object" ? primary : {};
  const merged: Record<string, unknown> = { ...base, ...override };
  const baseRag = base.rag && typeof base.rag === "object" ? (base.rag as Record<string, unknown>) : {};
  const overrideRag = override.rag && typeof override.rag === "object" ? (override.rag as Record<string, unknown>) : {};
  if (Object.keys(baseRag).length || Object.keys(overrideRag).length) {
    merged.rag = { ...baseRag, ...overrideRag };
  }
  return Object.keys(merged).length ? merged : undefined;
}

function mergeResource(primary: ResourceLink, secondary?: ResourceLink): ResourceLink {
  if (!secondary) return primary;
  return {
    ...secondary,
    ...primary,
    metadata: mergeMetadata(primary.metadata, secondary.metadata),
  };
}

function mergeResourceLists(bundleResources: ResourceLink[] | undefined, libraryResources: ResourceLink[] | undefined) {
  const bundle = bundleResources ?? [];
  const library = libraryResources ?? [];
  if (!bundle.length) return library;
  const libraryByKey = new Map<string, ResourceLink>();
  library.forEach((resource) => {
    resourceKeys(resource).forEach((key) => {
      if (!libraryByKey.has(key)) libraryByKey.set(key, resource);
    });
  });
  const used = new Set<ResourceLink>();
  const merged = bundle.map((resource) => {
    const match = resourceKeys(resource).map((key) => libraryByKey.get(key)).find(Boolean);
    if (match) used.add(match);
    return mergeResource(resource, match);
  });
  const extras = library.filter((resource) => !used.has(resource));
  return [...merged, ...extras];
}

function resourceType(resource: ResourceLink) {
  return String(resource.type || resource.source || "").toLowerCase();
}

function matchesResourceFilter(resource: ResourceLink, filter: ResourceFilterId) {
  const type = resourceType(resource);
  if (filter === "all") return true;
  if (filter === "local") return Boolean(resource.local_href);
  if (filter === "materialized") return Boolean(resource.local_href) || SUCCESSFUL_RESOURCE_STATUSES.has(resource.status || "");
  if (filter === "failed") return resource.status === "failed";
  if (filter === "link-only") return resource.status === "link-only";
  if (filter === "paper") return type.includes("paper") || type.includes("论文");
  if (filter === "repository") return type.includes("repository") || type.includes("github") || type.includes("code");
  if (filter === "book-course") return ["book", "course", "textbook"].some((item) => type.includes(item)) || type.includes("书") || type.includes("课程");
  return true;
}

function resourcePurpose(resource: ResourceLink) {
  const type = resourceType(resource);
  const combined = [resource.title, resource.label, resource.source, resource.type, resource.status, resource.url, resource.href, resource.local_href]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  if (
    resource.status === "generated" ||
    type.includes("template") ||
    type.includes("validation") ||
    combined.includes("artifact_template") ||
    combined.includes("checklist")
  ) {
    return { label: "验收材料", reason: "为什么读：把理解变成可提交、可复查的学习证据。" };
  }
  if (
    type.includes("repository") ||
    type.includes("github") ||
    type.includes("code") ||
    type.includes("notebook") ||
    type.includes("implementation")
  ) {
    return { label: "代码/复现", reason: "为什么读：把理解变成可运行或可检查的结果。" };
  }
  if (metadataIsTargetPaper(resource)) {
    return { label: "主证据", reason: "为什么读：定位论文原始论点、方法和实验结论。" };
  }
  if (
    type.includes("paper") ||
    type.includes("arxiv") ||
    type.includes("doi") ||
    combined.includes("paper.pdf")
  ) {
    return { label: "论文资料", reason: "为什么读：用于补充相关论点或对比证据，进入核心路径前需要结合证据核验。" };
  }
  if (
    type.includes("book") ||
    type.includes("course") ||
    type.includes("textbook") ||
    type.includes("article") ||
    type.includes("docs") ||
    type.includes("tutorial")
  ) {
    return { label: "背景补充", reason: "为什么读：补齐读懂论文所需的前置概念。" };
  }
  return { label: "辅助资料", reason: "为什么读：补充路线中还缺的上下文。" };
}

function numericScore(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function ragEvidenceScore(resource: ResourceLink) {
  const rag = resource.metadata?.rag;
  if (!rag || typeof rag !== "object") return 0;
  return numericScore((rag as { evidence_score?: unknown }).evidence_score);
}

function evidenceChunkCandidates(resource: ResourceLink) {
  const candidates: Array<Record<string, unknown>> = [];
  const metadata = resource.metadata && typeof resource.metadata === "object" ? resource.metadata : {};
  const rag = metadata.rag && typeof metadata.rag === "object" ? (metadata.rag as Record<string, unknown>) : {};
  for (const key of ["evidence_chunks", "top_chunks", "chunks"]) {
    const value = rag[key] ?? metadata[key];
    if (Array.isArray(value)) {
      candidates.push(...value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object"));
    }
  }
  return candidates;
}

function evidenceReviewHref(item: Evidence, resource: ResourceLink) {
  const detailAnchor = String(item.detail_anchor || "").trim();
  if (detailAnchor) {
    if (/^https?:\/\//i.test(detailAnchor) || detailAnchor.startsWith("paper_lens.html")) return detailAnchor;
    return detailAnchor.startsWith("#") ? `paper_lens.html${detailAnchor}` : `paper_lens.html#${detailAnchor}`;
  }
  return item.local_href || item.href || item.url || resource.local_href || resource.href || resource.url || "";
}

function strongestEvidence(resource: ResourceLink) {
  const best = evidenceChunkCandidates(resource)
    .map((item) => ({
      snippet: String(item.snippet || item.text || "").trim(),
      score: numericScore(item.score),
      href: evidenceReviewHref(item as Evidence, resource),
    }))
    .filter((item) => item.snippet)
    .sort((a, b) => b.score - a.score || b.snippet.length - a.snippet.length)[0];
  return best || null;
}

function strongestEvidenceSnippet(resource: ResourceLink) {
  return strongestEvidence(resource)?.snippet || "";
}

function formatResourceScore(value: number) {
  return value.toFixed(2);
}

function resourceStrengthReason(resource: ResourceLink) {
  const parts: string[] = [];
  const evidence = ragEvidenceScore(resource);
  const trust = numericScore(resource.trust_score);
  const rank = numericScore(resource.score);
  if (resource.local_href) parts.push("本地可打开");
  else if (resource.status === "link-only") parts.push("仅链接");
  else if (resource.status === "failed") parts.push("下载失败");
  else if (resource.status === "generated") parts.push("生成模板");
  if (evidence > 0) parts.push(`证据分 ${formatResourceScore(evidence)}`);
  if (trust > 0) parts.push(`可信分 ${formatResourceScore(trust)}`);
  if (rank > 0) parts.push(`推荐分 ${formatResourceScore(rank)}`);
  if (!parts.length) parts.push("需要手动核验");
  return `依据：${parts.join(" / ")}`;
}

function resourceStrength(resource: ResourceLink) {
  const trust = numericScore(resource.trust_score);
  const rank = numericScore(resource.score);
  const evidence = Math.min(1, ragEvidenceScore(resource) / 3);
  const best = Math.max(trust, rank, evidence);
  if (resource.status === "link-only" || resource.status === "failed") {
    return { label: "手动兜底", evidenceLabel: best >= 0.65 ? "证据强度：中" : "证据强度：待核验" };
  }
  if (resource.status === "generated") {
    return { label: "手动兜底", evidenceLabel: "证据强度：待填充" };
  }
  if (best >= 0.88) {
    return { label: "核心资料", evidenceLabel: "证据强度：高" };
  }
  if (best >= 0.65 || resource.local_href) {
    return { label: "推荐补充", evidenceLabel: best >= 0.78 ? "证据强度：中高" : "证据强度：中" };
  }
  return { label: "手动兜底", evidenceLabel: "证据强度：待核验" };
}

function lowerResourceText(resource: ResourceLink) {
  const metadata = resource.metadata && typeof resource.metadata === "object" ? JSON.stringify(resource.metadata) : "";
  return [
    resource.title,
    resource.label,
    resource.source,
    resource.type,
    resource.status,
    resource.url,
    resource.href,
    resource.local_href,
    resource.language,
    resource.why_recommended,
    resource.critical_path_role,
    ...(resource.concepts ?? []),
    ...(resource.learning_key_points ?? []),
    ...(resource.focus_areas ?? []),
    strongestEvidenceSnippet(resource),
    metadata,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function sourceKey(resource: ResourceLink) {
  return [
    resource.source,
    resource.type,
    resource.status,
    resource.url,
    resource.href,
    resource.local_href,
    resource.title,
    resource.label,
    resource.critical_path_role,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function resourceProvenance(resource: ResourceLink) {
  const key = sourceKey(resource);
  const metadata = resource.metadata && typeof resource.metadata === "object" ? resource.metadata : {};
  if (metadata.target_paper || key.includes("target paper")) {
    return {
      label: "目标论文",
      detail: "这份资料是路线的中心证据，优先用于核对原始论点、方法和实验。",
      level: "core",
    };
  }
  if (resource.status === "generated" || key.includes("template") || key.includes("artifact_template")) {
    return {
      label: "生成模板",
      detail: "由 fields-study-flow 生成，用来记录复现过程和验收证据，不替代真实实验结果。",
      level: "template",
    };
  }
  if (key.includes("arxiv") || key.includes("semantic-scholar") || key.includes("openalex") || key.includes("doi")) {
    return {
      label: "开放学术源",
      detail: "来自开放论文索引或 DOI 元数据，适合做论文级证据入口。",
      level: "academic",
    };
  }
  if (key.includes("github") || key.includes("repository") || key.includes("code") || key.includes("notebook")) {
    return {
      label: "代码来源",
      detail: "适合验证实现、运行示例或检查复现实验线索；仍需看维护状态。",
      level: "code",
    };
  }
  if (resource.local_href || key.includes("local-library") || key.includes("local://")) {
    return {
      label: "本地资料",
      detail: "已经进入本地资料包，适合离线阅读和回到证据片段复核。",
      level: "local",
    };
  }
  if (resource.status === "link-only" || resource.status === "failed") {
    return {
      label: "待手动核验",
      detail: "当前主要是链接入口，需要手动打开或补下载后再作为核心证据。",
      level: "manual",
    };
  }
  return {
    label: "候选来源",
    detail: "可作为补充资料；建议结合证据片段和任务需求判断是否必读。",
    level: "candidate",
  };
}

const COVERAGE_LABELS: Record<string, string> = {
  background: "背景",
  motivation: "动机/缺口",
  problem: "问题",
  methodology: "方法",
  experiment: "实验",
  result: "结果",
  contribution: "贡献",
  limitation: "局限",
  formula: "公式",
  resource: "资料",
  task: "任务",
  assessment: "验收",
};

function metadataIsTargetPaper(resource: ResourceLink) {
  const metadata = resource.metadata && typeof resource.metadata === "object" ? resource.metadata : {};
  return Boolean(metadata.target_paper || lowerResourceText(resource).includes("target paper"));
}

function resourceCoverage(resource: ResourceLink, roadmap: Roadmap) {
  const text = lowerResourceText(resource);
  const labels = new Set<string>();
  const targetPaper = metadataIsTargetPaper(resource);
  (roadmap.paper_map?.nodes ?? []).forEach((node) => {
    const kind = String(node.kind || node.role || "").toLowerCase();
    const label = String(node.label || node.kind_label || "").toLowerCase();
    const display = COVERAGE_LABELS[kind] || node.kind_label || node.label;
    if (!display) return;
    if (kind && text.includes(kind)) labels.add(String(display));
    else if (label.length >= 4 && text.includes(label.slice(0, Math.min(label.length, 24)))) labels.add(String(display));
  });
  const type = resourceType(resource);
  if (targetPaper) ["背景", "方法", "实验"].forEach((item) => labels.add(item));
  if (type.includes("repository") || type.includes("code") || type.includes("notebook")) ["方法", "实验", "复现"].forEach((item) => labels.add(item));
  if (type.includes("book") || type.includes("course") || type.includes("textbook") || type.includes("tutorial")) labels.add("背景");
  if (resource.status === "generated" || type.includes("template") || text.includes("checklist")) labels.add("验收");
  const snippet = strongestEvidenceSnippet(resource).toLowerCase();
  if (snippet.includes("limitation") || snippet.includes("future work")) labels.add("局限");
  if (snippet.includes("contribution") || snippet.includes("claim")) labels.add("贡献");
  const items = [...labels].slice(0, 5);
  const prefix = targetPaper ? "覆盖" : "推断覆盖";
  return {
    items,
    detail: items.length ? `${prefix} ${items.length} 个学习面：${items.join(" / ")}` : "尚未匹配到明确论文环节，适合作为补充阅读或手动核验资料。",
  };
}

function taskProgressKey(roadmap: Roadmap) {
  return `fields-study-flow:task-progress:${roadmap.title || roadmap.profile?.goal || "roadmap"}`;
}

function readTaskProgress(key: string) {
  try {
    const raw = window.localStorage?.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.map(String) : []);
  } catch {
    return new Set<string>();
  }
}

function writeTaskProgress(key: string, value: Set<string>) {
  try {
    window.localStorage?.setItem(key, JSON.stringify([...value]));
  } catch {
    // Local progress is a convenience; reports remain usable without storage.
  }
}

function taskId(task: StudyTask, index: number) {
  return String(task.id || `${task.type || "task"}-${index + 1}`);
}

function taskEvidenceCount(task?: StudyTask) {
  if (!task) return 0;
  const resources = Array.isArray(task.resource_titles) ? task.resource_titles.filter(Boolean).length : 0;
  const chunks = Array.isArray(task.evidence_chunks) ? task.evidence_chunks.filter(isTraceableEvidenceChunk).length : 0;
  return resources + chunks;
}

function isTraceableEvidenceChunk(chunk: unknown) {
  if (typeof chunk === "string") return Boolean(chunk.trim());
  if (!chunk || typeof chunk !== "object") return false;
  const record = chunk as Record<string, unknown>;
  const snippet = String(record.snippet || record.text || record.quote || "").trim();
  const locator = ["detail_anchor", "local_href", "href", "url", "file_name", "resource_title"].some((key) => Boolean(record[key]));
  return Boolean(snippet || locator);
}

function masteryGateStatusLabel(status: MasteryGateStatus) {
  if (status === "ready") return "已可验收";
  if (status === "needs_evidence") return "缺证据";
  return "缺任务";
}

function buildMasteryReadiness(tasks: StudyTask[]) {
  const items = MASTERY_GATE_ORDER.map((gate) => {
    const matchingTasks = tasks.filter((task) => String(task.type || "").toLowerCase() === gate.type);
    const task = matchingTasks.sort((a, b) => taskEvidenceCount(b) - taskEvidenceCount(a))[0];
    const evidenceCount = taskEvidenceCount(task);
    const status: MasteryGateStatus = task ? (evidenceCount > 0 ? "ready" : "needs_evidence") : "missing";
    const score = status === "ready" ? 2 : status === "needs_evidence" ? 1 : 0;
    return {
      ...gate,
      task,
      evidenceCount,
      status,
      score,
      action: status === "ready" ? gate.readyAction : status === "needs_evidence" ? gate.needsAction : gate.missingAction,
    };
  });
  const maxScore = items.length * 2;
  const score = items.reduce((total, item) => total + item.score, 0);
  const percent = maxScore ? Math.round((score / maxScore) * 100) : 0;
  return { items, score, maxScore, percent };
}

function PaperSetPanel({ paperSet }: { paperSet: NonNullable<Roadmap["paper_set"]> }) {
  const papers = paperSet.papers ?? [];
  const readingOrder = paperSet.reading_order ?? [];
  const sharedConcepts = paperSet.shared_concepts ?? [];
  const comparisonAxes = paperSet.comparison_axes ?? [];
  const synthesisTasks = paperSet.synthesis_tasks ?? [];
  const readingItems = readingOrder.length
    ? readingOrder
    : papers.map((paper, index) => ({
        position: index + 1,
        paper_id: paper.id,
        title: paper.title,
        role: paper.role,
        reason: undefined as string | undefined,
      }));
  if (!papers.length && !readingOrder.length && !sharedConcepts.length) return null;
  return (
    <section className="paper-set-panel" data-paper-set-panel aria-labelledby="paper-set-title">
      <div className="paper-set-head">
        <div>
          <p className="eyebrow">{"\u591a\u7bc7\u8bba\u6587\u6a21\u5f0f"}</p>
          <h2 id="paper-set-title">{"\u6587\u732e\u7ec4\u7efc\u5408 / Paper set synthesis"}</h2>
          <p>{paperSet.summary?.purpose || "Compare the papers as one reading set, then synthesize shared concepts, method differences, evidence, and limitations."}</p>
        </div>
        <div className="paper-set-stats" aria-label="paper set summary">
          <span><strong>{paperSet.summary?.paper_count ?? papers.length}</strong>{"\u7bc7\u8bba\u6587"}</span>
          <span><strong>{paperSet.summary?.selected_paper_count ?? papers.filter((paper) => paper.selected).length}</strong>{"\u6761\u4e3b\u8def\u5f84"}</span>
          <span><strong>{paperSet.summary?.shared_concept_count ?? sharedConcepts.length}</strong>{"\u4e2a\u5171\u540c\u6982\u5ff5"}</span>
        </div>
      </div>
      <div className="paper-set-grid">
        <article className="paper-set-card paper-set-reading">
          <h3>{"\u5efa\u8bae\u9605\u8bfb\u987a\u5e8f"}</h3>
          <ol>
            {readingItems.map((item, index) => (
              <li key={`${item.paper_id || item.title}-${index}`}>
                <span>{item.position ?? index + 1}</span>
                <div>
                  <strong>{item.title || "\u672a\u547d\u540d\u8bba\u6587"}</strong>
                  {item.reason ? <p>{item.reason}</p> : null}
                </div>
              </li>
            ))}
          </ol>
        </article>
        <article className="paper-set-card">
          <h3>{"\u5171\u540c\u6982\u5ff5"}</h3>
          <div className="paper-set-chip-list">
            {sharedConcepts.length ? sharedConcepts.map((concept) => (
              <span className="paper-set-chip" key={concept.label}>
                {concept.label}<b>{concept.paper_count ?? concept.paper_ids?.length ?? 0}</b>
              </span>
            )) : <p className="subtle">{"\u6682\u672a\u627e\u5230\u8de8\u8bba\u6587\u5171\u540c\u6982\u5ff5\u3002"}</p>}
          </div>
        </article>
        <article className="paper-set-card">
          <h3>{"\u6a2a\u5411\u5bf9\u6bd4\u7ef4\u5ea6"}</h3>
          <div className="paper-set-axis-list">
            {comparisonAxes.map((axis) => (
              <div key={axis.id || axis.label}>
                <strong>{axis.label}</strong>
                {axis.prompt ? <p>{axis.prompt}</p> : null}
              </div>
            ))}
          </div>
        </article>
        <article className="paper-set-card">
          <h3>{"\u7efc\u5408\u4efb\u52a1"}</h3>
          <div className="paper-set-task-list">
            {synthesisTasks.map((task, index) => (
              <div key={`${task.type}-${index}`}>
                <span>{task.type || "\u4efb\u52a1"}</span>
                <p>{task.title}</p>
              </div>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}

export function RoadmapApp({ roadmap }: { roadmap: Roadmap }) {
  const phases = roadmap.phases ?? [];
  const studyTasks = roadmap.study_tasks ?? [];
  const studyBundle = roadmap.study_bundle;
  const bundle = studyBundle?.summary ?? {};
  const resources = useMemo(
    () => mergeResourceLists(roadmap.study_bundle?.resources, roadmap.resource_library),
    [roadmap.study_bundle?.resources, roadmap.resource_library],
  );
  const [resourceQuery, setResourceQuery] = useState("");
  const [resourceFilter, setResourceFilter] = useState<ResourceFilterId>("all");
  const progressKey = useMemo(() => taskProgressKey(roadmap), [roadmap]);
  const [completedTaskIds, setCompletedTaskIds] = useState<Set<string>>(() => readTaskProgress(progressKey));
  const [worksheetState, setWorksheetState] = useState<"idle" | "copied" | "downloaded" | "failed">("idle");
  const hasPaperMap = Boolean(roadmap.paper_map);
  const hasPaperLens = Boolean(roadmap.paper_lens);
  const localResourceCount = resources.filter((resource) => resource.local_href).length;
  const totalResourceCount = resources.length;
  const bundleTotal = numeric(bundle.total) || totalResourceCount;
  const bundleCompleted =
    numeric(bundle.completed) ||
    resources.filter((resource) => resource.local_href || SUCCESSFUL_RESOURCE_STATUSES.has(resource.status || "")).length;
  const bundleRate = bundleTotal ? Math.round((bundleCompleted / bundleTotal) * 100) : 0;
  const statusCards = [
    { label: "本地可打开", value: localResourceCount },
    { label: "已下载", value: summaryCount(bundle, resources, "downloaded") },
    { label: "已复制", value: summaryCount(bundle, resources, "copied") },
    { label: "已快照", value: summaryCount(bundle, resources, "snapshotted") },
    { label: "生成模板", value: summaryCount(bundle, resources, "generated") },
    { label: "下载失败", value: summaryCount(bundle, resources, "failed") },
    { label: "仅链接", value: summaryCount(bundle, resources, "link-only") },
  ];
  const bundleFileLinks = [
    { label: "打开资料包说明", href: studyBundle?.readme_href, meta: studyBundle?.readme_file || "README.md" },
    { label: "原始链接清单", href: studyBundle?.links_href, meta: studyBundle?.links_file || "links.md" },
    { label: "重试失败项", href: studyBundle?.retry_href, meta: studyBundle?.download_manager?.retry_file || "retry_failed.md" },
    { label: "下载队列", href: studyBundle?.download_queue_href, meta: studyBundle?.download_manager?.download_queue_file || "download_queue.json" },
  ].filter((item) => item.href);
  const orderedResources = useMemo(() => [...resources].sort((a, b) => {
    const aLocal = a.local_href ? 0 : 1;
    const bLocal = b.local_href ? 0 : 1;
    if (aLocal !== bLocal) return aLocal - bLocal;
    const aFailed = a.status === "failed" ? 0 : 1;
    const bFailed = b.status === "failed" ? 0 : 1;
    if (aFailed !== bFailed) return aFailed - bFailed;
    return String(a.title || a.label || "").localeCompare(String(b.title || b.label || ""), "zh-CN");
  }), [resources]);
  const filteredResources = useMemo(() => {
    const query = resourceQuery.trim().toLowerCase();
    return orderedResources.filter((resource) => {
      if (!matchesResourceFilter(resource, resourceFilter)) return false;
      if (!query) return true;
      return resourceSearchText(resource, roadmap).includes(query);
    });
  }, [orderedResources, resourceFilter, resourceQuery, roadmap.paper_map]);
  const completedTaskCount = studyTasks.filter((task, index) => completedTaskIds.has(taskId(task, index))).length;
  const taskProgressRate = studyTasks.length ? Math.round((completedTaskCount / studyTasks.length) * 100) : 0;
  const masteryWorksheet = useMemo(
    () => buildMasteryWorksheet(roadmap, studyTasks, completedTaskIds),
    [roadmap, studyTasks, completedTaskIds],
  );
  const masteryReadiness = useMemo(() => buildMasteryReadiness(studyTasks), [studyTasks]);
  const missingPhases = phases.length === 0;
  const missingTasks = studyTasks.length === 0;
  const missingResources = resources.length === 0;
  const routeRecoveryItems = [
    missingPhases
      ? {
          title: "补齐学习阶段",
          detail: "重新生成路线或补充目标论文、领域目标，让报告能拆成可执行阶段。",
          action: "建议：重新运行 paper/roadmap，并保留 --resource-dir。",
        }
      : null,
    missingResources
      ? {
          title: "补充目标论文或本地资料",
          detail: "添加 PDF、README、Notebook 或代码仓库后重跑，让路线有证据和本地入口。",
          action: "建议：使用 --local-resource 或 --resource-dir。",
        }
      : null,
    missingTasks
      ? {
          title: "补齐验收任务",
          detail: "至少生成解释、推导、复现、批判中的三个验收动作，否则很难判断是否掌握。",
          action: "建议：保留 paper 模式或选择 practical 学习风格。",
        }
      : null,
  ].filter(Boolean) as Array<{ title: string; detail: string; action: string }>;
  const hasRouteGaps = routeRecoveryItems.length > 0;
  useEffect(() => {
    writeTaskProgress(progressKey, completedTaskIds);
  }, [completedTaskIds, progressKey]);
  function toggleTask(taskKey: string) {
    setCompletedTaskIds((current) => {
      const next = new Set(current);
      if (next.has(taskKey)) next.delete(taskKey);
      else next.add(taskKey);
      return next;
    });
  }
  async function copyMasteryWorksheet() {
    try {
      if (!navigator.clipboard?.writeText) {
        setWorksheetState("failed");
        return;
      }
      await navigator.clipboard.writeText(masteryWorksheet);
      setWorksheetState("copied");
    } catch {
      setWorksheetState("failed");
    }
  }
  function downloadMasteryWorksheet() {
    try {
      const blob = new Blob([`${masteryWorksheet}\n`], { type: "text/markdown;charset=utf-8" });
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = "mastery_worksheet.md";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
      setWorksheetState("downloaded");
    } catch {
      setWorksheetState("failed");
    }
  }
  const startSteps = [
    {
      title: "1 先看论文逻辑图",
      detail: "用 XMind 式因果图先抓住背景、动机、问题、方法、实验、贡献和局限。",
      href: "paper_map.html",
      enabled: hasPaperMap,
      meta: hasPaperMap ? "推荐 5-10 分钟建立全局框架" : "当前报告未生成论文逻辑图",
    },
    {
      title: "2 再做段落精读",
      detail: "只读关键段落，把原文、直白解释、证据和资料放在同一个阅读流里。",
      href: "paper_lens.html",
      enabled: hasPaperLens,
      meta: hasPaperLens ? "推荐 20-40 分钟读懂关键段落" : "当前报告未生成段落精读",
    },
    {
      title: "3 最后按任务验收",
      detail: "按阶段完成解释、推导、复现和批判，把学习结果变成能检查的证据。",
      href: "#learning-phases",
      enabled: phases.length > 0,
      meta: phases.length ? `${phases.length} 个学习阶段` : "暂无阶段任务",
    },
    {
      title: "资料包随时打开",
      detail: "下载后的论文、网页快照、代码和模板优先走本地链接，避免重新到处找资料。",
      href: "#resource-library",
      enabled: totalResourceCount > 0,
      meta: localResourceCount ? `${localResourceCount}/${totalResourceCount} 个本地可打开` : `${totalResourceCount} 个资料入口`,
    },
  ];
  const firstMinuteSteps = [
    { time: "00:00", title: "先点论文逻辑图", detail: "先看主链，建立论文整体框架。" },
    { time: "00:30", title: "打开一份本地资料", detail: "确认资料包能直接阅读，优先看目标论文。" },
    { time: "01:00", title: "勾掉第一个验收任务", detail: "把阅读动作变成可检查进度。" },
  ];
  return (
    <main className="report-app">
      <Header
        roadmap={roadmap}
        eyebrow="学习中控台"
        title={roadmap.title || "fields-study-flow 学习路线"}
        actions={
          <>
            {roadmap.paper_map ? <a className="primary-action" href="paper_map.html">进入论文逻辑图</a> : null}
            {roadmap.paper_lens ? <a className="pill-link" href="paper_lens.html">进入段落精读</a> : null}
          </>
        }
      />
      <section className="start-panel" aria-labelledby="start-panel-title">
        <div className="start-panel-copy">
          <p className="eyebrow">推荐打开顺序</p>
          <h2 id="start-panel-title">先从这里开始</h2>
          <p>这份报告的目标不是堆资料，而是让你用最短路径抓住论文逻辑、读懂关键段落，并完成可验收的掌握任务。</p>
          <div className="first-minute-card" aria-label="1分钟上手">
            <strong>1分钟上手</strong>
            <ol>
              {firstMinuteSteps.map((step) => (
                <li key={step.title}>
                  <span>{step.time}</span>
                  <div>
                    <b>{step.title}</b>
                    <p>{step.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
        <div className="start-grid">
          {startSteps.map((step) => {
            const body = (
              <>
                <span>{step.meta}</span>
                <h3>{step.title}</h3>
                <p>{step.detail}</p>
              </>
            );
            return step.enabled ? (
              <a className="start-card" href={step.href} key={step.title}>
                {body}
              </a>
            ) : (
              <div className="start-card disabled" aria-disabled="true" key={step.title}>
                {body}
              </div>
            );
          })}
        </div>
      </section>
      {roadmap.paper_set ? <PaperSetPanel paperSet={roadmap.paper_set} /> : null}
      <section className="bundle-dashboard" aria-labelledby="bundle-dashboard-title">
        <div className="bundle-progress">
          <p className="eyebrow">资料包状态</p>
          <h2 id="bundle-dashboard-title">资料包完成率</h2>
          <strong>{bundleRate}%</strong>
          <div className="bundle-progress-bar" aria-label={`资料包完成率 ${bundleRate}%`}>
            <span style={{ width: `${Math.max(0, Math.min(100, bundleRate))}%` }} />
          </div>
          <p>{bundleCompleted}/{bundleTotal || totalResourceCount} 个资料已落地或已生成；失败和仅链接资料仍会保留入口，方便手动补齐。</p>
        </div>
        <div className="bundle-status-grid">
          {statusCards.map((item) => (
            <article className={item.label === "下载失败" && item.value ? "bundle-status-card attention" : "bundle-status-card"} key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </article>
          ))}
        </div>
        {bundleFileLinks.length ? (
          <div className="bundle-action-row" aria-label="资料包文件入口">
            {bundleFileLinks.map((item) => (
              <a href={item.href} key={item.label}>
                <strong>{item.label}</strong>
                <span>{item.meta}</span>
              </a>
            ))}
          </div>
        ) : null}
      </section>
      <section className="dashboard-grid">
        <article className="metric-card">
          <span>总耗时</span>
          <strong>{roadmap.path_strategy?.estimated_total_time || "待估计"}</strong>
        </article>
        <article className="metric-card">
          <span>路线模式</span>
          <strong>{roadmap.path_strategy?.mode || roadmap.profile?.route_depth || "balanced"}</strong>
        </article>
        <article className="metric-card">
          <span>资料包</span>
          <strong>{String(bundle.downloaded ?? bundle.copied ?? bundle.resources ?? resources.length ?? 0)}</strong>
        </article>
      </section>
      {hasRouteGaps ? (
        <section className="route-recovery-panel" data-route-recovery aria-labelledby="route-recovery-title">
          <div className="route-recovery-copy">
            <p className="eyebrow">路线自检</p>
            <h2 id="route-recovery-title">下一步补齐路线</h2>
            <p>当前报告缺少能直接指导学习的关键部件。先按下面动作补齐，再生成报告，学习路径会更像可执行产品而不是空白模板。</p>
          </div>
          <div className="route-recovery-grid">
            {routeRecoveryItems.map((item) => (
              <article className="route-recovery-card" key={item.title}>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
                <span>{item.action}</span>
              </article>
            ))}
          </div>
        </section>
      ) : null}
      <section className="roadmap-readiness-panel" data-roadmap-mastery-readiness data-mastery-readiness-panel aria-labelledby="roadmap-readiness-title">
        <div className="roadmap-readiness-head">
          <div>
            <p className="eyebrow">掌握就绪</p>
            <h2 id="roadmap-readiness-title">现在离真正掌握还差什么</h2>
            <p>按解释、推导、复现、批判四个门槛检查：有任务且有资料证据才算已可验收。</p>
          </div>
          <div className="roadmap-readiness-score" aria-label={`掌握就绪 ${masteryReadiness.percent}%`}>
            <strong>{masteryReadiness.percent}%</strong>
            <span>{masteryReadiness.score}/{masteryReadiness.maxScore}</span>
          </div>
        </div>
        <div className="roadmap-readiness-grid">
          {masteryReadiness.items.map((item) => (
            <a
              className={`roadmap-readiness-card status-${item.status}`}
              href="#mastery-checklist-title"
              data-roadmap-mastery-gate={item.type}
              data-roadmap-mastery-status={item.status}
              data-mastery-gate={item.type}
              data-mastery-status={item.status}
              key={item.type}
            >
              <span>{item.label}</span>
              <strong>{masteryGateStatusLabel(item.status)}</strong>
              <p>{item.action}</p>
              {item.task ? <em>{item.task.title || `${item.label}任务`} · 证据 {item.evidenceCount}</em> : <em>暂无对应任务</em>}
            </a>
          ))}
        </div>
      </section>
      {studyTasks.length ? (
        <section className="mastery-checklist-panel" aria-labelledby="mastery-checklist-title">
          <div className="mastery-checklist-head">
            <div>
              <p className="eyebrow">掌握验收</p>
              <h2 id="mastery-checklist-title">把学习变成可检查证据</h2>
              <p>勾选只保存在当前浏览器；正式掌握仍以解释、推导、复现和批判产物为准。</p>
            </div>
            <div className="mastery-progress-box">
              <strong>{completedTaskCount}/{studyTasks.length} · {taskProgressRate}%</strong>
              <div className="mastery-export-actions" data-mastery-export>
                <button type="button" onClick={copyMasteryWorksheet}>复制证据清单</button>
                <button type="button" onClick={downloadMasteryWorksheet}>下载 worksheet.md</button>
              </div>
              <span aria-live="polite">
                {worksheetState === "copied" ? "已复制，可粘贴到笔记或汇报文档。" : null}
                {worksheetState === "downloaded" ? "已生成 mastery_worksheet.md 下载。" : null}
                {worksheetState === "failed" ? "当前浏览器限制自动操作，可手动复制任务内容。" : null}
              </span>
            </div>
          </div>
          <div className="mastery-task-grid">
            {studyTasks.map((task, index) => {
              const id = taskId(task, index);
              const checked = completedTaskIds.has(id);
              return (
                <article className={checked ? "mastery-task-card done" : "mastery-task-card"} key={id}>
                  <label>
                    <input type="checkbox" checked={checked} onChange={() => toggleTask(id)} />
                    <span>{TASK_TYPE_LABELS[task.type || ""] || task.type || "任务"}</span>
                  </label>
                  <h3>{task.title || `验收任务 ${index + 1}`}</h3>
                  <p>{task.evidence || "完成后留下可复查的学习证据。"}</p>
                  <small>{task.acceptance || "能解释给别人听，并能回到论文证据。"}{task.estimated_minutes ? ` · ${task.estimated_minutes} 分钟` : ""}</small>
                  {(task.resource_titles ?? []).length ? <em>{(task.resource_titles ?? []).slice(0, 2).join(" / ")}</em> : null}
                </article>
              );
            })}
          </div>
        </section>
      ) : (
        <section className="mastery-checklist-panel empty-panel" aria-labelledby="mastery-checklist-title">
          <div className="mastery-checklist-head">
            <div>
              <p className="eyebrow">掌握验收</p>
              <h2 id="mastery-checklist-title">暂无验收任务</h2>
              <p>补齐 explain / derive / reproduce / critique 任务后，这里会变成可勾选的本地进度轨。</p>
            </div>
          </div>
        </section>
      )}
      <section className="content-grid">
        <div className="panel" id="learning-phases">
          <h2>学习阶段</h2>
          <div className="phase-list">
            {phases.length ? phases.map((phase, index) => (
              <article className="phase-card" key={`${phase.name}-${index}`}>
                <span className="phase-index">{index + 1}</span>
                <div>
                  <h3>{phase.name || `阶段 ${index + 1}`}</h3>
                  <p>{phase.objective || "按路线完成这一阶段的关键资料和验收任务。"}</p>
                  <span className="subtle">{phase.estimated_time}</span>
                </div>
              </article>
            )) : (
              <div className="empty-state route-empty-state">
                <strong>暂无学习阶段</strong>
                <p>先补齐目标论文、领域目标或本地资料后重新生成路线。</p>
              </div>
            )}
          </div>
        </div>
        <aside className="panel resource-library-panel" id="resource-library">
          <div className="resource-library-header">
            <div>
              <h2>本地资料入口</h2>
              <p>先看本地可打开资料；失败和仅链接资料保留在这里，方便后续补齐。</p>
            </div>
            <span>{filteredResources.length}/{resources.length}</span>
          </div>
          <label className="resource-search">
            <span>搜索资料</span>
            <input
              aria-label="搜索资料"
              value={resourceQuery}
              onChange={(event) => setResourceQuery(event.target.value)}
              placeholder="输入论文、书籍、代码、状态或来源"
            />
          </label>
          <div className="resource-filter-chips" aria-label="资料筛选">
            {RESOURCE_FILTERS.map((filter) => (
              <button
                type="button"
                key={filter.id}
                className={resourceFilter === filter.id ? "active" : ""}
                data-resource-filter={filter.id}
                onClick={() => setResourceFilter(filter.id)}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <div className="resource-list">
            {resources.length === 0 ? (
              <div className="empty-state route-empty-state">
                <strong>暂无可打开资料</strong>
                <p>添加 --resource-dir 或 --local-resource 后重新生成资料包。</p>
              </div>
            ) : filteredResources.length ? filteredResources.map((resource, index) => {
              const purpose = resourcePurpose(resource);
              const strength = resourceStrength(resource);
              const strengthReason = resourceStrengthReason(resource);
              const evidence = strongestEvidence(resource);
              const provenance = resourceProvenance(resource);
              const coverage = resourceCoverage(resource, roadmap);
              return (
                <div className="resource-row" key={`${resource.title}-${index}`}>
                  <div>
                    <strong>{resource.title || resource.label || "资料"}</strong>
                    <p>{[resource.type || resource.source || "resource", resourceStatusLabel(resource.status)].filter(Boolean).join(" / ")}</p>
                    <div className="resource-purpose-line">
                      <span className="resource-purpose-badge">{purpose.label}</span>
                      <span>{purpose.reason}</span>
                    </div>
                    <div className="resource-strength-line">
                      <span className="resource-strength-badge">{strength.label}</span>
                      <span>{strength.evidenceLabel}</span>
                      <span className="resource-strength-reason">{strengthReason}</span>
                      {resource.why_recommended ? <span>推荐理由：{resource.why_recommended}</span> : null}
                    </div>
                    <div className="resource-provenance-line">
                      <span className={`resource-provenance-badge ${provenance.level}`}>{provenance.label}</span>
                      <span>{provenance.detail}</span>
                    </div>
                    <div className="resource-coverage-line">
                      <span className="resource-coverage-badge">覆盖范围</span>
                      {coverage.items.map((item) => <span className="resource-coverage-chip" key={item}>{item}</span>)}
                      <span>{coverage.detail}</span>
                    </div>
                    {evidence ? (
                      <p className="resource-evidence-snippet">
                        <span>最强证据：{evidence.snippet}</span>
                        {evidence.href ? <a className="resource-evidence-link" href={evidence.href}>查看证据</a> : null}
                      </p>
                    ) : null}
                  </div>
                  <ResourceButton item={resource} label={resource.local_href ? "打开本地" : "打开链接"} />
                </div>
              );
            }) : (
              <div className="empty-state">没有匹配的资料。可以清空搜索词，或切回“全部资料”。</div>
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}
