import { useCallback, useEffect, useMemo, useState } from "react";
import { FileText, Focus } from "lucide-react";
import { Empty, ResourceButton } from "./shared";
import type { PaperLensSegment, Roadmap } from "./types";
import { targetPaperLink } from "./data";
import { WorkbenchProvider, useWorkbench } from "./workbench/WorkbenchProvider";
import { WorkbenchLayout } from "./workbench/WorkbenchLayout";
import { ContextPanel, DetailBlock } from "./workbench/ContextPanel";
import { bindParagraph } from "./workbench/paragraphBinding";

export function PaperLensApp({ roadmap }: { roadmap: Roadmap }) {
  return <WorkbenchProvider roadmap={roadmap}><PaperLensWorkbench /></WorkbenchProvider>;
}
function PaperLensWorkbench() {
  const { roadmap, context, study, t, showContext, pageHref } = useWorkbench();
  const lens = roadmap.paper_lens || {};
  const segments = useMemo(() => lens.segments || [], [lens.segments]);
  const explanations = useMemo(() => lens.inline_explanations || [], [lens.inline_explanations]);
  function segmentFromHash() {
    let id = ""; try { id = decodeURIComponent(location.hash.slice(1)); } catch { return undefined; }
    return segments.find(s => `segment-${s.id}` === id || s.id === id)
      || segments.find(s => explanations.some(e => e.segment_id === s.id && (e.detail_anchor === id || e.id === id)));
  }
  const [activeId, setActiveId] = useState(() => segmentFromHash()?.id || study.state.selection.segmentId || segments[0]?.id || "");
  const active = segments.find(s => s.id === activeId) || segments[0];
  const explanation = explanations.find(e => e.segment_id === active?.id);
  const binding = bindParagraph(context, active);
  const claim = binding.claim;
  const selectParagraph = useCallback((segment: PaperLensSegment, reveal = true) => {
    const binding = bindParagraph(context, segment);
    const related = binding.claim;
    const step = context.learning_steps.find(s => s.claim_ids.includes(related?.id || segment.id));
    setActiveId(segment.id);
    study.select({ segmentId: segment.id, claimId: related?.id, anchorId: binding.anchorIds[0] || related?.anchor_ids[0], stepId: step?.id, taskId: undefined });
    history.replaceState(null, "", `#segment-${encodeURIComponent(segment.id)}`);
    if (reveal) showContext();
  }, [context, study.select, showContext]);
  useEffect(() => {
    function onHash() {
      let hash = ""; try { hash = decodeURIComponent(location.hash.slice(1)); } catch { return; }
      const segment = segments.find(s => `segment-${s.id}` === hash || s.id === hash)
        || segments.find(s => explanations.some(e => e.segment_id === s.id && (e.detail_anchor === hash || e.id === hash)));
      if (segment) {
        selectParagraph(segment, false);
        document.getElementById(`segment-${segment.id}`)?.scrollIntoView?.({ block: "nearest", behavior: "instant" });
      }
    }
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [segments, explanations, selectParagraph]);
  useEffect(() => {
    const selected = study.state.selection;
    if (selected.segmentId && segments.some(s => s.id === selected.segmentId) && selected.segmentId !== activeId) {
      setActiveId(selected.segmentId);
    } else if (selected.claimId) {
      const related = context.claims.find(c => c.id === selected.claimId);
      const segment = related ? segments.find(s => bindParagraph(context, s).claim?.id === related.id) : undefined;
      if (segment && segment.id !== activeId) setActiveId(segment.id);
    }
  }, [study.state.selection, context, segments, activeId]);
  const sections = [...new Map(segments.map(s => [s.section_kind || s.section_title || "", s])).values()];
  const recommended = (lens.reading_recommendations || []).filter(r => r.section_title === active?.section_title);
  const target = targetPaperLink(roadmap);
  return <WorkbenchLayout page="paper_lens" actions={<>
    {target && <ResourceButton item={target} label={t("openSource")} />}
    {lens.latex_export?.pdf_file && <ResourceButton item={{ local_href: lens.latex_export.pdf_file }} label={t("pdf")} />}
    {lens.latex_export?.tex_file && <ResourceButton item={{ local_href: lens.latex_export.tex_file }} label={t("tex")} />}
  </>} context={<ContextPanel title={active?.section_title || active?.section_kind} claimId={claim?.id || null} anchorIds={binding.anchorIds} includeStudyAnchors={false}
    evidence={claim?.anchor_ids.length ? [] : explanation?.evidence_refs}
    recommendations={recommended.length ? <section className="detail-section"><h3>{t("recommended")}</h3>{recommended.map((r, i) => <div key={i}><p>{r.summary}</p>{(r.resources || []).map((item, j) => <ResourceButton key={j} item={item} />)}</div>)}</section> : undefined}>
    <DetailBlock title={t("explanation")} text={explanation?.plain_meaning || claim?.statement} />
    <DetailBlock title={t("why")} text={explanation?.why_it_matters} />
    <DetailBlock title={t("method")} text={explanation?.method_note} />
  </ContextPanel>}>
    <div className="reading-workspace">
      <nav className="section-strip" aria-label={t("sections")}>{sections.map(s => <a key={s.id} href={`#segment-${encodeURIComponent(s.id)}`}
        aria-current={active?.section_kind === s.section_kind ? "location" : undefined}>{s.section_title || s.section_kind}</a>)}</nav>
      <div className="paragraph-stream">
        {segments.length ? segments.map((segment, index) => <article key={segment.id} id={`segment-${segment.id}`}
          className={`paragraph-card ${active?.id === segment.id ? "active" : ""}`} data-section-kind={segment.section_kind}>
          <div className="paragraph-heading"><span><FileText size={14} />{segment.section_title || segment.section_kind || t("paragraph")}</span>
            <button type="button" className="paragraph-select" aria-label={`${t("selectParagraph")} ${index + 1}`} title={`${t("selectParagraph")} ${index + 1}`}
              aria-pressed={active?.id === segment.id} onClick={() => selectParagraph(segment)}><Focus size={16} /><span>{index + 1}</span></button>
          </div>
          <p className="original-paragraph">{segment.original_text}</p>
        </article>) : <Empty>{t("noParagraphs")}</Empty>}
      </div>
      {claim && !roadmap.paper_map_disabled && <a className="reading-graph-link" href={pageHref("paper_map.html", claim.id)}>{t("graph")}</a>}
    </div>
  </WorkbenchLayout>;
}
