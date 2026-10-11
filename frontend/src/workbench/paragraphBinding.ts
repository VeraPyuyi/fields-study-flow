import type { PaperLensSegment, ResearchContext } from "../types";

export function normalizedSectionKind(kind?: string): string | undefined {
  const aliases: Record<string, string> = { method: "methodology", methods: "methodology", abstract: "background", related_work: "background", results: "result", limitations: "limitation" };
  const value = aliases[kind || ""] || kind;
  return ["background", "motivation", "problem", "methodology", "experiment", "result", "contribution", "limitation"].includes(value || "") ? value : undefined;
}

export function bindParagraph(context: ResearchContext, segment?: PaperLensSegment) {
  if (!segment) return { claim: undefined, anchorIds: [] as string[] };
  const anchorIds = segment.anchor_ids?.length ? segment.anchor_ids : context.anchors
    .filter(a => !!segment.original_text && a.snippet === segment.original_text).map(a => a.id);
  const ids = new Set(anchorIds);
  const kind = normalizedSectionKind(segment.section_kind);
  const candidates = context.claims.filter(c => c.anchor_ids.some(id => ids.has(id)));
  const claim = context.claims.find(c => c.id === segment.claim_id || segment.claim_ids?.includes(c.id))
    || context.claims.find(c => c.id === segment.id)
    || (kind ? candidates.find(c => normalizedSectionKind(c.kind) === kind) : undefined)
    || candidates[0];
  return { claim, anchorIds };
}
