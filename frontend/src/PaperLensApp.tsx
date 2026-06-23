import { useMemo, useState } from "react";
import { Empty, Header, ResourceButton } from "./shared";
import type { PaperLensExplanation, PaperLensSegment, Roadmap } from "./types";
import { compactTitle, targetPaperLink, targetPaperTitle } from "./data";

export function PaperLensApp({ roadmap }: { roadmap: Roadmap }) {
  const lens = roadmap.paper_lens ?? {};
  const target = targetPaperLink(roadmap);
  const title = lens.title || targetPaperTitle(roadmap) || roadmap.title || "论文精读";
  const segments = lens.segments ?? [];
  const explanations = lens.inline_explanations ?? [];
  const [activeId, setActiveId] = useState(segments[0]?.id || "");
  const explanationBySegment = useMemo(() => {
    const map = new Map<string, PaperLensExplanation>();
    explanations.forEach((item) => {
      if (item.segment_id) map.set(item.segment_id, item);
    });
    return map;
  }, [explanations]);
  const sectionAnchors = useMemo(() => firstSegmentAnchors(segments), [segments]);
  const confidenceStats = useMemo(() => supportSummary(explanations), [explanations]);
  const activeSegment = segments.find((segment) => segment.id === activeId) || segments[0];
  const activeExplanation = activeSegment ? explanationBySegment.get(activeSegment.id) : undefined;

  return (
    <main className="lens-app">
      <Header
        roadmap={roadmap}
        eyebrow="段落式论文精读"
        title={title}
        actions={
          <>
            <a className="primary-action" href="paper_map.html">进入论文逻辑图</a>
            {target ? <ResourceButton item={target} label={target.local_href ? "打开目标论文" : "打开原始论文"} /> : null}
            {lens.latex_export?.pdf_file ? <a className="pill-link" href={lens.latex_export.pdf_file}>打开 PDF 精简版</a> : null}
          </>
        }
      />
      {confidenceStats ? (
        <section className="confidence-explainer" aria-label="解释支撑度说明">
          <div>
            <span>段落解释支撑度</span>
            <strong>{confidenceStats.rangeLabel}</strong>
          </div>
          <p>它表示这段解释得到多少原文、资料和本地证据支撑；不是资源可信度，也不是绝对正确率。分数越高越适合优先汇报，关键结论仍建议回到原文复核。</p>
          <small>{confidenceStats.uniqueCount} 档分值 · {confidenceStats.count} 个段落解释</small>
        </section>
      ) : null}
      <section className="lens-layout">
        <aside className="section-nav">
          <h2>阅读导航</h2>
          {(lens.sections ?? []).map((section) => {
            const href = sectionAnchors.get(section.kind || "") || "";
            return href ? (
              <a key={section.kind || section.title} href={`#${href}`}>
                {section.title || section.kind}
              </a>
            ) : (
              <span className="nav-static" key={section.kind || section.title}>{section.title || section.kind}</span>
            );
          })}
          <div className="lens-summary">
            <span>精读粒度</span>
            <strong>{lens.explanation_summary?.granularity === "sentence" ? "句子" : "段落"}</strong>
          </div>
          <details className="nav-recommendations">
            <summary>集中推荐阅读</summary>
            {(lens.reading_recommendations ?? []).length ? (
              (lens.reading_recommendations ?? []).map((item, index) => (
                <div className="recommendation-card" key={`${item.section_title}-${index}`}>
                  <strong>{item.section_title || "推荐资料"}</strong>
                  <p>{item.summary}</p>
                  <div className="button-row compact">
                    {(item.resources ?? []).slice(0, 3).map((resource, resourceIndex) => (
                      <ResourceButton
                        key={`${resource.title}-${resourceIndex}`}
                        item={resource}
                        label={resource.local_href ? "打开本地" : resource.title || "打开资料"}
                      />
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <Empty>暂未生成集中推荐资料。</Empty>
            )}
          </details>
        </aside>
        <div className="paragraph-stream">
          {segments.length ? (
            segments.map((segment) => (
              <ParagraphCard
                key={segment.id}
                segment={segment}
                explanation={explanationBySegment.get(segment.id)}
                active={segment.id === activeSegment?.id}
                onSelect={() => setActiveId(segment.id)}
              />
            ))
          ) : (
            <Empty>暂未找到可用于段落精读的论文片段。请确认目标 PDF 能被解析，或在资料包中加入论文文本。</Empty>
          )}
        </div>
        <aside className="detail-rail">
          <p className="eyebrow">当前段落解释</p>
          <h2>{activeSegment?.section_title || activeSegment?.section_kind || "选择一个段落"}</h2>
          <Detail title="这段在说什么" text={activeExplanation?.plain_meaning} />
          <Detail title="为什么重要" text={activeExplanation?.why_it_matters} />
          <Detail title="方法怎么理解" text={activeExplanation?.method_note} />
          <details className="detail-section collapsible-section">
            <summary>相关资料（按需展开）</summary>
            <div className="button-row">
              {(activeExplanation?.related_resources ?? []).length ? (
                (activeExplanation?.related_resources ?? []).map((resource, index) =>
                  typeof resource === "string" ? <span className="tag" key={index}>{resource}</span> : <ResourceButton key={index} item={resource} />,
                )
              ) : (
                <Empty>推荐资料已集中放在左侧导航里，避免每段重复打断阅读。</Empty>
              )}
            </div>
          </details>
          <section className="detail-section">
            <h3>原文证据</h3>
            {(activeExplanation?.evidence_refs ?? []).length ? (
              (activeExplanation?.evidence_refs ?? []).slice(0, 3).map((item, index) => (
                <blockquote key={index}>
                  <strong>{item.resource_title || item.file_name || "证据"}</strong>
                  <p>{item.snippet || item.note}</p>
                </blockquote>
              ))
            ) : (
              <Empty>当前段落还没有绑定证据片段。</Empty>
            )}
          </section>
        </aside>
      </section>
    </main>
  );
}

function supportSummary(explanations: PaperLensExplanation[]) {
  const values = explanations
    .map((item) => Number(item.confidence))
    .filter((value) => Number.isFinite(value));
  if (!values.length) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const minLabel = supportLabel(min);
  const maxLabel = supportLabel(max);
  const levelLabel = minLabel === maxLabel ? minLabel : `${minLabel}-${maxLabel}`;
  return {
    count: values.length,
    uniqueCount: new Set(values.map((value) => value.toFixed(2))).size,
    rangeLabel: min === max ? supportText(min) : `${levelLabel}（${min.toFixed(2)}-${max.toFixed(2)}）`,
  };
}

function supportLabel(value: number): string {
  if (value >= 0.86) return "高";
  if (value >= 0.74) return "中";
  return "低";
}

function supportText(value: number): string {
  return `${supportLabel(value)}（${value.toFixed(2)}）`;
}

function firstSegmentAnchors(segments: PaperLensSegment[]): Map<string, string> {
  const anchors = new Map<string, string>();
  segments.forEach((segment) => {
    const kind = segment.section_kind || "";
    if (kind && !anchors.has(kind)) {
      anchors.set(kind, segmentAnchorId(segment));
    }
  });
  return anchors;
}

function segmentAnchorId(segment: PaperLensSegment): string {
  return `segment-${segment.id}`;
}

function ParagraphCard({
  segment,
  explanation,
  active,
  onSelect,
}: {
  segment: PaperLensSegment;
  explanation?: PaperLensExplanation;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <article id={segmentAnchorId(segment)} className={`paragraph-card ${active ? "active" : ""}`} data-section-kind={segment.section_kind}>
      <button type="button" onClick={onSelect}>
        <span>{segment.section_title || segment.section_kind || "论文段落"}</span>
        <strong>{compactTitle(segment.original_text, 320)}</strong>
      </button>
      <p>{active ? "右侧正在显示这段的直白解释、方法理解和证据。" : "点击这段，在右侧查看专属解释。"}</p>
      <div className="segment-meta">
        <span className="tag">段落 {segment.paragraph_index || segment.id}</span>
        <span className="tag">{segment.sentence_count || 1} 句</span>
        <span className="tag">重要度 {segment.importance_score ?? "-"}</span>
        {explanation?.confidence ? <span className="tag support-tag">解释支撑度：{supportText(Number(explanation.confidence))}</span> : null}
      </div>
    </article>
  );
}

function Detail({ title, text }: { title: string; text?: string }) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      <p>{text || "暂无解释。"}</p>
    </section>
  );
}
