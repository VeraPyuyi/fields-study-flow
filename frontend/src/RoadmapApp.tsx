import { useEffect, useMemo, useState } from "react";
import { Focus, Search } from "lucide-react";
import { Empty, ResourceButton } from "./shared";
import type { LearningStep, ResourceLink, Roadmap, StudyTask } from "./types";
import { linkHref } from "./data";
import { allResources } from "./workbench/adapter";
import { WorkbenchProvider, useWorkbench } from "./workbench/WorkbenchProvider";
import { WorkbenchLayout } from "./workbench/WorkbenchLayout";
import { ContextPanel, DetailBlock } from "./workbench/ContextPanel";
import { domainLabel } from "./workbench/domainLabels";
import { LearningIssues, learningStepLabel } from "./workbench/learningStatus";

export function RoadmapApp({ roadmap }: { roadmap: Roadmap }) {
  return <WorkbenchProvider roadmap={roadmap}><LearningWorkbench /></WorkbenchProvider>;
}
function LearningWorkbench() {
  const { roadmap, context, study, t, language, pageHref, showContext } = useWorkbench();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "local" | "failed" | "linked">("all");
  const [taskOnly, setTaskOnly] = useState(false);
  const [typeFilter, setTypeFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [routeFilter, setRouteFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [resourceId, setResourceId] = useState<string | null>(null);
  const resources = useMemo(() => allResources(roadmap), [roadmap]);
  const tasks = useMemo(() => (roadmap.study_tasks || []).map((task, i) => ({ ...task, id: task.id || `task-${i}` })), [roadmap.study_tasks]);
  const unboundTasks = tasks.filter(task => !context.learning_steps.some(s => s.task_ids.includes(task.id)));
  const selectedTask = tasks.find(task => task.id === study.state.selection.taskId);
  const step = selectedTask ? undefined : context.learning_steps.find(s => s.id === study.state.selection.stepId) || context.learning_steps[0];
  const stepTasks = selectedTask ? [selectedTask] : tasks.filter(task => step?.task_ids.includes(task.id));
  const selectedSource = context.sources.find(s => s.id === resourceId);
  const sourceIds = new Set(context.anchors.filter(a => step?.anchor_ids.includes(a.id)
    || context.claims.some(c => step?.claim_ids.includes(c.id) && c.anchor_ids.includes(a.id))).map(a => a.source_id));
  function findSource(item: ResourceLink) {
    const exact = context.sources.find(s => s.id === item.id)
      || context.sources.find(s => !!item.local_href && s.local_href === item.local_href)
      || context.sources.find(s => !!(item.url || item.href) && s.url === (item.url || item.href));
    if (exact) return exact;
    const byTitle = context.sources.filter(s => s.title === item.title);
    return byTitle.length === 1 && !((item.url || item.href) && byTitle[0].url && byTitle[0].url !== (item.url || item.href)) ? byTitle[0] : undefined;
  }
  const resourceCards: ResourceLink[] = [...resources];
  context.sources.forEach(s => {
    if (!resourceCards.some(r => (r.local_href && r.local_href === s.local_href) || (r.url && r.url === s.url) || (!r.url && !s.url && r.title === s.title))) resourceCards.push({ id: s.id, title: s.title, local_href: s.local_href, url: s.url, type: s.kind });
  });
  const route = (item: ResourceLink) => String(item.route_status || item.metadata?.route_status || item.metadata?.route_selection
    || (item.status === "generated" ? "generated" : item.selected === true || item.metadata?.selected === true ? "selected" : item.selected === false || item.metadata?.selected === false ? "omitted" : "unknown"));
  const options = (field: (item: ResourceLink) => string) => [...new Set(resourceCards.map(field))].filter(Boolean).sort();
  const searchable = useMemo(() => new Map(resources.map(item => [item, JSON.stringify(item).toLowerCase()])), [resources]);
  const visible = resourceCards.filter(item => {
    const source = findSource(item);
    if (taskOnly && !sourceIds.has(source?.id || "") && !stepTasks.some(task => task.resource_titles?.includes(item.title || ""))) return false;
    if (filter === "local" && !item.local_href) return false;
    if (filter === "failed" && item.status !== "failed") return false;
    if (filter === "linked" && item.local_href) return false;
    if (typeFilter !== "all" && item.type !== typeFilter) return false;
    if (sourceFilter !== "all" && item.source !== sourceFilter) return false;
    if (routeFilter !== "all" && route(item) !== routeFilter) return false;
    if (statusFilter !== "all" && item.status !== statusFilter) return false;
    return (searchable.get(item) || `${item.title || ""} ${item.type || ""}`).toLowerCase().includes(search.toLowerCase().trim());
  });
  useEffect(() => {
    function hash() {
      let id = ""; try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
      const selected = context.learning_steps.find(s => s.id === id);
      const task = unboundTasks.find(task => task.id === id);
      if (selected) study.select({ stepId: selected.id, claimId: selected.claim_ids[0], anchorId: selected.anchor_ids[0], taskId: undefined });
      else if (task) study.select({ taskId: task.id, stepId: undefined, claimId: task.claim_ids?.[0], anchorId: task.anchor_ids?.[0] });
    }
    hash(); window.addEventListener("hashchange", hash);
    return () => window.removeEventListener("hashchange", hash);
  }, [context, study.select]);
  function selectStep(selected: LearningStep) {
    setResourceId(null);
    study.select({ stepId: selected.id, claimId: selected.claim_ids[0], anchorId: selected.anchor_ids[0], segmentId: undefined, taskId: undefined });
    history.replaceState(null, "", `#${encodeURIComponent(selected.id)}`);
    showContext();
  }
  function selectTask(task: StudyTask & { id: string }) {
    setResourceId(null);
    study.select({ taskId: task.id, stepId: undefined, claimId: task.claim_ids?.[0], anchorId: task.anchor_ids?.[0], segmentId: undefined });
    history.replaceState(null, "", `#${encodeURIComponent(task.id)}`);
    showContext();
  }
  const sourceAnchors = selectedSource ? context.anchors.filter(a => a.source_id === selectedSource.id).map(a => a.id) : selectedTask?.anchor_ids || step?.anchor_ids;
  const stepLabel = step ? learningStepLabel(step, context, language, roadmap.profile?.learning_outcome) : undefined;
  return <WorkbenchLayout page="roadmap" context={<ContextPanel title={selectedSource?.title || selectedTask?.title || stepLabel} anchorIds={sourceAnchors}
    stepId={selectedTask ? null : step?.id} taskId={selectedTask?.id} claimId={selectedTask ? selectedTask.claim_ids?.[0] || null : undefined}
    evidence={selectedTask?.evidence_chunks}>
    <DetailBlock title={t("why")} text={selectedSource ? undefined : step?.reason} />
    {!selectedSource && step && context.claims.filter(c => step.claim_ids.includes(c.id)).map(c => <DetailBlock key={c.id} title={t("claim")} text={c.statement} />)}
    {!selectedSource && (step?.questions || []).map((question, i) => <DetailBlock key={i} title={`${t("tasks")} ${i + 1}`} text={question} />)}
    {!selectedSource && (step?.check_points || []).map((point, i) => <DetailBlock key={i} title={`${t("acceptance")} ${i + 1}`} text={point} />)}
    {!selectedSource && stepTasks.map((task, i) => <section className="detail-section" key={task.id || i}><h3>{task.title}</h3><p>{task.evidence}</p><p>{task.acceptance}</p><div className="button-row">{resources.filter(r => task.resource_titles?.includes(r.title || "")).map((r, j) => <ResourceButton key={j} item={r} />)}</div></section>)}
  </ContextPanel>}>
    <div className="learning-surface">
      <section className="learning-section"><h2>{t("steps")}</h2>
        {context.learning_steps.length ? <ol className="step-overview">{context.learning_steps.map((item, i) => <li id={item.id} key={item.id}>
          <button type="button" className={step?.id === item.id ? "active" : ""} aria-pressed={step?.id === item.id} onClick={() => selectStep(item)}>
            <span className="step-number">{i + 1}</span><span><strong>{learningStepLabel(item, context, language, roadmap.profile?.learning_outcome)}</strong><LearningIssues step={item} /><small>{study.state.records[item.id]?.stale ? t("stale") : t(study.state.records[item.id]?.status || "not_started")}</small></span>
            <small>{item.estimated_minutes ? `${item.estimated_minutes} ${t("minutes")}` : t("estimate")}</small>
          </button>
          <p>{item.reason}</p>
          {item.prerequisite_ids.length > 0 && <div className="prerequisite-links"><span>{t("prerequisites")}</span>{item.prerequisite_ids.map(id => {
            const required = context.learning_steps.find(s => s.id === id); return required ? <a key={id} href={`#${encodeURIComponent(id)}`}>{required.title}</a> : null;
          })}</div>}
          <div className="button-row">{!roadmap.paper_map_disabled && item.claim_ids.length > 0 && <a href={pageHref("paper_map.html", item.claim_ids[0])}>{t("graph")}</a>}{[...new Set(item.anchor_ids.map(id => context.anchors.find(a => a.id === id)?.source_id))].map(id => {
            const source = context.sources.find(s => s.id === id);
            return source ? <ResourceButton key={id} item={source} /> : null;
          })}</div>
        </li>)}</ol> : <Empty>{t("noSteps")}</Empty>}
      </section>
      {unboundTasks.length > 0 && <section className="learning-section unbound-tasks"><h2>{t("unboundTasks")}</h2>
        {unboundTasks.map(task => <article key={task.id} id={task.id} className="unbound-task">
          <button type="button" aria-pressed={selectedTask?.id === task.id} onClick={() => selectTask(task)}>{task.title || domainLabel(task.type || "task", language)}</button>
          <small>{study.state.records[task.id]?.stale ? t("stale") : t(study.state.records[task.id]?.status || "not_started")}</small>
          <p>{task.evidence}</p>
        </article>)}
      </section>}
      <section className="learning-section" id="resource-library" data-resource-library><div className="section-heading"><h2>{t("resources")}</h2><span>{visible.length}/{resourceCards.length}</span></div>
        <div className="resource-tools"><label className="search-field"><Search size={16} /><input aria-label={t("search")} placeholder={t("search")} value={search} onChange={e => setSearch(e.target.value)} /></label>
          <div className="segmented-control">{(["all", "local", "failed", "linked"] as const).map(id => <button type="button" key={id} aria-pressed={filter === id} onClick={() => setFilter(id)}>{t(id)}</button>)}</div>
          <label className="filter-toggle"><input type="checkbox" checked={taskOnly} onChange={e => setTaskOnly(e.target.checked)} />{t("taskOnly")}</label>
          <div className="resource-filter-menus">
            <select aria-label={t("typeFilter")} value={typeFilter} onChange={e => setTypeFilter(e.target.value)}><option value="all">{t("typeFilter")}: {t("all")}</option>{options(r => r.type || "").map(value => <option value={value} key={value}>{domainLabel(value, language)}</option>)}</select>
            <select aria-label={t("sourceFilter")} value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}><option value="all">{t("sourceFilter")}: {t("all")}</option>{options(r => r.source || "").map(value => <option value={value} key={value}>{value}</option>)}</select>
            <select aria-label={t("routeFilter")} value={routeFilter} onChange={e => setRouteFilter(e.target.value)}><option value="all">{t("routeFilter")}: {t("all")}</option>{options(route).map(value => <option value={value} key={value}>{domainLabel(value, language)}</option>)}</select>
            <select aria-label={t("statusFilter")} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="all">{t("statusFilter")}: {t("all")}</option>{options(r => r.status || "").map(value => <option value={value} key={value}>{domainLabel(value, language)}</option>)}</select>
          </div>
        </div>
        <div className="resource-list">{visible.length ? visible.map((item, i) => {
          const source = findSource(item);
          const rag = item.metadata?.rag as { evidence_chunks?: unknown[] } | undefined;
          const evidence = item.metadata?.evidence_chunks || rag?.evidence_chunks;
          return <article className="resource-item" key={`${item.title}-${i}`}>
            <div className="resource-item-heading"><h3>{item.title || item.label || t("resources")}</h3><button type="button" className="icon-button" aria-label={`${t("context")} ${item.title || i}`} title={t("context")}
              onClick={() => { setResourceId(source?.id || null); const anchor = context.anchors.find(a => a.source_id === source?.id); study.select({ anchorId: anchor?.id }); showContext(); }}><Focus size={16} /></button></div>
            <div className="resource-meta"><span>{item.type ? domainLabel(item.type, language) : ""}</span><span className={item.status === "failed" ? "warning" : ""}>{item.local_href ? t("local") : item.status === "failed" ? t("failed") : t("linked")}</span></div>
            <div className="button-row"><ResourceButton item={item} label={t(item.local_href ? "openLocal" : "openSource")} />
              {item.local_href && linkHref({ url: item.url || item.href }) && <ResourceButton item={{ url: item.url || item.href }} label={t("remote")} />}</div>
            <details><summary>{t("context")}</summary><p>{item.why_recommended}</p>
              {(item.learning_key_points || []).map((point, j) => <p key={j}>{point}</p>)}
              {Array.isArray(evidence) && evidence.map((e, j) => {
                const chunk = e as { snippet?: string; text?: string; note?: string };
                return <blockquote key={j}>{String(chunk.snippet || chunk.text || chunk.note || "")}</blockquote>;
              })}
            </details>
          </article>;
        }) : <Empty>{t("noResources")}</Empty>}</div>
      </section>
      {(roadmap.phases || []).length > 0 && <details className="learning-section"><summary>{t("phases")}</summary>{roadmap.phases!.map((phase, i) => <section className="phase-item" key={i}><h3>{phase.name}</h3><p>{phase.objective}</p><div className="button-row">{(phase.resources || []).map((r, j) => <ResourceButton key={j} item={r} />)}</div></section>)}</details>}
      {roadmap.paper_set && <details className="learning-section"><summary>{t("paperSet")}</summary>{(roadmap.paper_set.papers || []).map((paper, i) => <section className="phase-item" key={paper.id || i}><h3>{paper.title}</h3><p>{(paper.concepts || []).join(", ")}</p></section>)}
        {(roadmap.paper_set.shared_concepts || []).map((concept, i) => <p key={i}>{concept.label}</p>)}
        <ol>{(roadmap.paper_set.reading_order || []).map((item, i) => <li key={item.paper_id || i}><h3>{item.title}</h3><p>{item.reason}</p></li>)}</ol>
        {(roadmap.paper_set.comparison_axes || []).map((axis, i) => <DetailBlock key={axis.id || i} title={axis.label || t("paperSet")} text={axis.prompt} />)}
        {(roadmap.paper_set.synthesis_tasks || []).map((task, i) => <DetailBlock key={i} title={task.title || t("tasks")} text={(task.evidence || []).join("\n")} />)}</details>}
      {roadmap.study_bundle && <details className="learning-section"><summary>{t("downloads")}</summary><div className="button-row">{([
        ["manifest", roadmap.study_bundle.manifest_href || roadmap.study_bundle.manifest_file],
        ["readme", roadmap.study_bundle.readme_href || roadmap.study_bundle.readme_file],
        ["remote", roadmap.study_bundle.links_href || roadmap.study_bundle.links_file],
        ["retry", roadmap.study_bundle.retry_href || roadmap.study_bundle.download_manager?.retry_file],
        ["queue", roadmap.study_bundle.download_queue_href || roadmap.study_bundle.download_manager?.download_queue_file],
      ] as const).map(([key, href]) => <ResourceButton key={key} item={{ local_href: href }} label={t(key)} />)}</div></details>}
    </div>
  </WorkbenchLayout>;
}
