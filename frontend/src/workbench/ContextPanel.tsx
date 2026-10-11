import { useEffect, useState, type ReactNode } from "react";
import { BookOpen, Code2, FlaskConical, NotebookPen } from "lucide-react";
import { Empty, ResourceButton } from "../shared";
import { linkHref } from "../data";
import type { Evidence, ResourceLink, SourceAnchor } from "../types";
import { useWorkbench } from "./WorkbenchProvider";
import { StudyRecordEditor } from "./StudyRecordEditor";
import { domainLabel } from "./domainLabels";

export function DetailBlock({ title, text }: { title: string; text?: string }) {
  if (!text) return null;
  return <section className="detail-section"><h3>{title}</h3><p>{text}</p></section>;
}
export function anchorHref(anchor: SourceAnchor, href: string): string {
  return anchor.locator.page && /\.pdf(?:[?#]|$)/i.test(href) && !href.includes("#") ? `${href}#page=${anchor.locator.page}` : href;
}

export function ContextPanel({ title, claimId, stepId, taskId, anchorIds = [], children, evidence = [], resources = [], recommendations, includeStudyAnchors = true }: {
  title?: string; claimId?: string | null; anchorIds?: string[]; children?: ReactNode; evidence?: Evidence[];
  stepId?: string | null; taskId?: string;
  includeStudyAnchors?: boolean;
  resources?: ResourceLink[]; recommendations?: ReactNode;
}) {
  const { context, study, t, pageHref, language } = useWorkbench();
  const [tab, setTab] = useState<"original" | "implementation" | "results" | "notes">("original");
  const selection = study.state.selection;
  const step = stepId === null ? undefined : context.learning_steps.find(s => s.id === (stepId || selection.stepId));
  const claim = claimId === null ? undefined : context.claims.find(c => c.id === (claimId || selection.claimId));
  const relations = context.relations.filter(r => r.from === claim?.id || r.to === claim?.id);
  const selectedIds = new Set([...anchorIds, ...(claim?.anchor_ids || []), ...(includeStudyAnchors ? step?.anchor_ids || [] : []),
    ...relations.flatMap(r => r.anchor_ids), ...(includeStudyAnchors && selection.anchorId ? [selection.anchorId] : [])]);
  const anchors = context.anchors.filter(a => selectedIds.has(a.id));
  useEffect(() => {
    const source = context.sources.find(s => s.id === context.anchors.find(a => a.id === selection.anchorId)?.source_id);
    if (source) setTab(["code", "config", "notebook", "readme", "repository"].includes(source.kind) ? "implementation" : source.kind === "result" ? "results" : "original");
  }, [context, selection.anchorId]);
  const visible = anchors.filter(a => {
    const kind = context.sources.find(s => s.id === a.source_id)?.kind || "paper";
    return tab === "implementation" ? ["code", "config", "notebook", "readme", "repository"].includes(kind) : tab === "results" ? ["result", "experiment", "table"].includes(kind) : !["code", "config", "notebook", "readme", "repository", "result", "experiment", "table"].includes(kind);
  });
  const recordId = taskId || selection.taskId || step?.id || claim?.id || selection.segmentId;
  return <div className="context-panel">
    <h2>{title || step?.title || t("context")}</h2>{children}
    {claim && <div className="claim-status"><span className="status-badge warning">{t("unverified")}</span></div>}
    <div className="context-tabs" role="tablist" aria-label={t("context")}>{([
      ["original", BookOpen], ["implementation", Code2], ["results", FlaskConical], ["notes", NotebookPen],
    ] as const).map(([id, Icon]) => <button type="button" key={id} role="tab" title={t(id)} aria-selected={tab === id}
      aria-controls={`context-${id}`} onClick={() => setTab(id)}><Icon size={16} /><span>{t(id)}</span></button>)}</div>
    <section role="tabpanel" id={`context-${tab}`} aria-label={t(tab)}>
      {tab === "notes" ? recordId ? <StudyRecordEditor id={recordId} /> : <Empty>{t("noSteps")}</Empty> : <>
        {visible.map(anchor => {
          const source = context.sources.find(s => s.id === anchor.source_id);
          const href = linkHref(source);
          const locator = anchor.locator;
          const code = source && ["code", "config", "notebook"].includes(source.kind);
          const locatorLabel = [locator.page ? `${t("page")} ${locator.page}` : "", locator.section, locator.symbol,
            locator.line_start ? `${t("lines")} ${locator.line_start}${locator.line_end ? `-${locator.line_end}` : ""}` : "",
            locator.cell_id ? `${t("cell")} ${locator.cell_id}` : "", locator.json_pointer,
            locator.row !== undefined ? `${t("row")} ${locator.row}` : "", locator.column !== undefined ? `${t("column")} ${locator.column}` : ""].filter(Boolean).join(" / ");
          return <article className="source-excerpt" key={anchor.id} id={`anchor-${anchor.id}`}>
            <h3>{source?.title || anchor.source_id}</h3>
            <div className="locator-meta"><span>{locatorLabel}</span><span className={`status-badge ${["valid", "located"].includes(anchor.locator_status) ? "located" : "warning"}`}>
              {t(["valid", "located"].includes(anchor.locator_status) ? "located" : "unresolved")}</span></div>
            {code ? <pre className="code-excerpt"><code>{anchor.snippet.split("\n").map((line, i) => <span className="code-line" key={i}><span className="line-number">{(locator.line_start || 1) + i}</span>{line || " "}</span>)}</code></pre> : <blockquote>{anchor.snippet}</blockquote>}
            {href && <ResourceButton item={{ ...source, local_href: anchorHref(anchor, href) }} label={t(source?.local_href ? "openLocal" : "openSource")} />}
          </article>;
        })}
        {tab === "original" && evidence.map((item, i) => <article className="source-excerpt" key={i}><h3>{item.source_title || item.resource_title || item.file_name || t("evidence")}</h3><blockquote>{item.snippet || item.text || item.note}</blockquote><ResourceButton item={item} label={t("openSource")} /></article>)}
        {!visible.length && !(tab === "original" && evidence.length) && <Empty>{t("missing")}</Empty>}
        {tab === "original" && resources.length > 0 && <section className="detail-section"><h3>{t("resources")}</h3>{resources.map((item, i) => <ResourceButton item={item} key={i} />)}</section>}
        {tab === "original" && recommendations}
        {relations.length > 0 && <section className="detail-section"><h3>{t("connection")}</h3>{relations.map(r => <p key={r.id} className="relation-item"><span title={r.kind}>{domainLabel(r.kind, language)}</span><span className={`status-badge ${r.review_status === "accepted" ? "located" : "warning"}`}>{t(r.review_status === "accepted" ? "accepted" : r.review_status === "rejected" ? "rejected" : "unreviewed")}</span><small title={r.origin}>{domainLabel(r.origin, language)}</small></p>)}</section>}
      </>}
    </section>
    {step && <section className="detail-section"><h3>{t("tasks")}</h3><a href={pageHref("roadmap.html", step.id)}>{step.title}</a></section>}
  </div>;
}
