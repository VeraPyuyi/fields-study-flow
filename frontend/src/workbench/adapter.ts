import type { Evidence, PaperLensSegment, PaperMapNode, ResearchContext, ResearchSource, ResourceLink, Roadmap, SourceAnchor, StudyTask } from "../types";

export function fingerprint(value: unknown): string {
  const text = JSON.stringify(value);
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  return (hash >>> 0).toString(16);
}

export function allResources(roadmap: Roadmap): ResourceLink[] {
  const inputs = [...(roadmap.resource_library || []), ...(roadmap.study_bundle?.resources || []),
    ...(roadmap.phases || []).flatMap(p => p.resources || []), ...(roadmap.paper_map?.source_links || []),
    ...(roadmap.paper_lens?.target_papers || []), ...(roadmap.paper_map?.target ? [roadmap.paper_map.target] : [])];
  const output: ResourceLink[] = [];
  const materialized = new Set(["downloaded", "copied", "snapshotted", "generated"]);
  for (const item of inputs) {
    const matches = output.filter(r => {
      if (r.id && item.id) return r.id === item.id;
      if ((r.url || r.href) && (item.url || item.href)) return (r.url || r.href) === (item.url || item.href);
      if (r.local_href && item.local_href) return r.local_href === item.local_href;
      if (!r.title || r.title !== item.title) return false;
      const identities = new Set(inputs.filter(s => s.title === item.title).map(s => s.id || s.url || s.href).filter(Boolean));
      return identities.size <= 1;
    });
    if (matches.length !== 1) { output.push({ ...item }); continue; }
    const old = matches[0];
    const fresh = Object.fromEntries(Object.entries(item).filter(([, v]) => v !== undefined && v !== ""));
    const metadata = { ...old.metadata, ...item.metadata };
    if (old.metadata?.rag || item.metadata?.rag) metadata.rag = { ...(old.metadata?.rag as object), ...(item.metadata?.rag as object) };
    const status = materialized.has(old.status || "") && !materialized.has(item.status || "") ? old.status : item.status || old.status;
    Object.assign(old, fresh, { local_href: item.local_href || old.local_href, status, metadata });
  }
  return output;
}

const mapping = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const stringList = (v: unknown): v is string[] => Array.isArray(v) && v.every(item => typeof item === "string");
function validContext(value: unknown): value is ResearchContext {
  if (!mapping(value) || value.schema_version !== 1 || typeof value.bundle_id !== "string" || typeof value.snapshot_id !== "string") return false;
  const rules: Record<string, (entry: Record<string, unknown>) => boolean> = {
    sources: s => [s.id, s.kind, s.title, s.fingerprint].every(v => typeof v === "string"),
    anchors: a => [a.id, a.source_id, a.snippet, a.locator_status].every(v => typeof v === "string") && mapping(a.locator),
    claims: c => [c.id, c.kind, c.statement, c.evidence_status].every(v => typeof v === "string") && stringList(c.anchor_ids),
    relations: r => [r.id, r.from, r.to, r.kind, r.origin, r.review_status].every(v => typeof v === "string") && stringList(r.anchor_ids),
    learning_steps: s => [s.id, s.title, s.reason, s.status].every(v => typeof v === "string") && [s.claim_ids, s.prerequisite_ids, s.anchor_ids, s.task_ids].every(stringList),
  };
  return Object.entries(rules).every(([key, rule]) => Array.isArray(value[key]) && (value[key] as unknown[]).every(entry => mapping(entry) && rule(entry)));
}

export function adaptResearchContext(roadmap: Roadmap): ResearchContext {
  if (validContext(roadmap.research_context)) {
    const context = roadmap.research_context;
    return { ...context, sources: context.sources || [], anchors: context.anchors || [], claims: context.claims || [],
      relations: context.relations || [], learning_steps: (context.learning_steps || []).map(step => ({ ...step,
        questions: stringList(step.answer_questions) ? step.answer_questions : stringList(step.questions) ? step.questions : [],
        check_points: stringList(step.check_points) ? step.check_points : [],
        missing_prerequisite_ids: stringList(step.missing_prerequisite_ids) ? step.missing_prerequisite_ids : [] })),
      coverage: context.coverage ? { ...context.coverage,
        skipped: Array.isArray(context.coverage.skipped) ? context.coverage.skipped.filter(mapping) : [],
        input_analysis: Array.isArray(context.coverage.input_analysis) ? context.coverage.input_analysis.filter(mapping) : [],
        truncated: context.coverage.truncated === true || (Array.isArray(context.coverage.truncated) ? context.coverage.truncated : false) } : undefined };
  }
  const resources = allResources(roadmap);
  const sources: ResearchSource[] = resources.map((r, i) => ({ id: `legacy-source-${i}`, kind: r.type || "paper",
    title: r.title || r.label || "", fingerprint: fingerprint(r), local_href: r.local_href, url: r.url || r.href }));
  const anchors: SourceAnchor[] = [];
  function addEvidence(evidence: Evidence[], owner: string): string[] {
    return evidence.map((e, i) => {
      const title = e.source_title || e.resource_title || e.file_name || "";
      let source = sources.find(s => s.title === title && (!e.local_href || s.local_href === e.local_href));
      if (!source) {
        source = { id: `legacy-evidence-${owner}-${i}`, title, kind: "paper", fingerprint: fingerprint(e), local_href: e.local_href || e.href, url: e.url };
        sources.push(source);
      }
      const id = `legacy-anchor-${owner}-${i}`;
      anchors.push({ id, source_id: source.id, locator: {}, snippet: e.snippet || e.text || e.note || "", locator_status: "unresolved" });
      return id;
    });
  }
  const claims = (roadmap.paper_map?.nodes || []).map(n => ({ id: n.id, kind: n.kind || "claim",
    statement: n.plain_explanation || n.label || "", anchor_ids: addEvidence(n.evidence || [], n.id), evidence_status: "unverified" }));
  (roadmap.paper_lens?.segments || []).forEach(segment => {
    if (claims.some(c => c.id === segment.id)) return;
    const explanation = roadmap.paper_lens?.inline_explanations?.find(e => e.segment_id === segment.id);
    claims.push({ id: segment.id, kind: segment.section_kind || "paragraph", statement: explanation?.plain_meaning || segment.original_text || "",
      anchor_ids: addEvidence(explanation?.evidence_refs || [], segment.id), evidence_status: "unverified" });
  });
  const learning_steps = (roadmap.study_tasks || []).map((task, i) => {
    const id = task.id || `task-${i}`;
    return { id, title: task.title || task.type || "", claim_ids: [], prerequisite_ids: [],
      anchor_ids: addEvidence(task.evidence_chunks || [], id), task_ids: [id], estimated_minutes: task.estimated_minutes,
      reason: task.acceptance || task.evidence || "", status: "not_started" };
  });
  return { schema_version: 1, bundle_id: `legacy-${fingerprint([roadmap.title, roadmap.paper_map?.target?.url, resources.map(r => [r.title, r.url])])}`,
    snapshot_id: `legacy-${fingerprint(roadmap)}`, sources, anchors, claims, learning_steps,
    relations: (roadmap.paper_map?.edges || []).map((e, i) => ({ id: e.id || `legacy-edge-${i}`, from: e.from, to: e.to,
      kind: e.label || "related", anchor_ids: [], origin: "legacy", review_status: "unreviewed" })) };
}

export function graphData(roadmap: Roadmap, context: ResearchContext) {
  const nodes: PaperMapNode[] = roadmap.paper_map?.nodes?.length ? roadmap.paper_map.nodes : context.claims.map(c => ({
    id: c.id, kind: c.kind, label: c.kind, plain_explanation: c.statement,
  }));
  const ids = new Set(nodes.map(n => n.id));
  const edges = roadmap.paper_map?.edges?.length ? roadmap.paper_map.edges : context.relations.filter(r => ids.has(r.from) && ids.has(r.to))
    .map(r => ({ id: r.id, from: r.from, to: r.to, label: r.kind }));
  return { nodes, edges };
}

export function claimForNode(context: ResearchContext, node?: PaperMapNode) {
  return context.claims.find(c => c.id === node?.claim_id) || context.claims.find(c => node?.claim_ids?.includes(c.id))
    || context.claims.find(c => c.id === node?.id) || context.claims.find(c => c.kind === node?.kind);
}

export function anchorsForNode(context: ResearchContext, node?: PaperMapNode): string[] {
  const ids = new Set([node?.claim_id, ...(node?.claim_ids || [])]);
  const primary = claimForNode(context, node);
  return [...new Set([...(node?.anchor_ids || []), ...(primary?.anchor_ids || []), ...context.claims.filter(c => ids.has(c.id)).flatMap(c => c.anchor_ids)])];
}

export function nodeForClaim(nodes: PaperMapNode[], context: ResearchContext, id?: string) {
  return nodes.find(n => n.id === id || n.claim_id === id || n.claim_ids?.includes(id || ""))
    || nodes.find(n => claimForNode(context, n)?.id === id);
}

export function recordDependencies(context: ResearchContext, recordId: string, segments: PaperLensSegment[] = [], tasks: StudyTask[] = []) {
  const step = context.learning_steps.find(s => s.id === recordId);
  const segment = segments.find(s => s.id === recordId);
  const task = tasks.find((t, i) => (t.id || `task-${i}`) === recordId);
  const claimIds = new Set([recordId, segment?.claim_id, ...(segment?.claim_ids || []), ...(step?.claim_ids || []), ...(task?.claim_ids || [])]);
  const ids = new Set([...(step?.anchor_ids || []), ...(segment?.anchor_ids || []), ...(task?.anchor_ids || []),
    ...context.claims.filter(c => claimIds.has(c.id)).flatMap(c => c.anchor_ids)]);
  const anchors = context.anchors.filter(a => ids.has(a.id));
  const claims = context.claims.filter(c => claimIds.has(c.id));
  const sources = new Set(anchors.map(a => a.source_id));
  (task?.resource_titles || []).forEach(title => {
    const candidates = context.sources.filter(s => s.title === title);
    if (candidates.length === 1) sources.add(candidates[0].id);
  });
  return { step, segment, task, claims, anchors, sourceIds: [...sources] };
}
export function recordSourceIds(context: ResearchContext, recordId: string, segments: PaperLensSegment[] = [], tasks: StudyTask[] = []): string[] {
  return recordDependencies(context, recordId, segments, tasks).sourceIds;
}
