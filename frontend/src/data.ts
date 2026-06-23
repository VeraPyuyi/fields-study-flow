import type { ReportKind, ReportPayload, ResourceLink, Roadmap } from "./types";

export function readPayload(): Required<Pick<ReportPayload, "reportKind">> & { roadmap: Roadmap } {
  const script = document.getElementById("fields-study-flow-data");
  if (!script?.textContent) {
    return { reportKind: "roadmap", roadmap: { title: "fields-study-flow" } };
  }
  try {
    const parsed = JSON.parse(script.textContent) as ReportPayload;
    return {
      reportKind: normalizeReportKind(parsed.reportKind),
      roadmap: parsed.roadmap ?? { title: "fields-study-flow" },
    };
  } catch {
    return { reportKind: "roadmap", roadmap: { title: "fields-study-flow" } };
  }
}

function normalizeReportKind(value: unknown): ReportKind {
  return value === "paper_map" || value === "paper_lens" || value === "roadmap" ? value : "roadmap";
}

export function isChinese(roadmap: Roadmap): boolean {
  return (roadmap.profile?.output_language ?? "zh-CN") !== "en";
}

export function compactTitle(value?: string, limit = 72): string {
  void limit;
  const text = String(value || "fields-study-flow").trim();
  return text;
}

export function linkHref(item?: { local_href?: string; url?: string; href?: string }): string {
  const href = item?.local_href || item?.href || item?.url || "";
  return href.startsWith("local://") ? "" : href;
}

export function targetPaperTitle(roadmap: Roadmap): string {
  return (
    roadmap.paper_lens?.target_papers?.[0]?.title ||
    roadmap.paper_lens?.target?.title ||
    roadmap.paper_map?.target?.title ||
    ""
  );
}

export function targetPaperLink(roadmap: Roadmap): ResourceLink | undefined {
  return roadmap.paper_lens?.target_papers?.[0] || roadmap.paper_lens?.target || roadmap.paper_map?.target;
}

export function reportHeadingTitle(roadmap: Roadmap, fallbackTitle: string): string {
  return collapseRepeatedTail(stripRoadmapPrefix(targetPaperTitle(roadmap) || fallbackTitle || roadmap.title || ""));
}

export function cleanHeaderSubtitle(value?: string, heading?: string): string {
  const raw = normalizeSpaces(value || "");
  const compactHeading = compactAcademicTitle(collapseRepeatedTail(stripRoadmapPrefix(heading || "")));
  let text = collapseRepeatedTail(stripRoadmapPrefix(raw));
  if (compactHeading) {
    text = removeTrailingHeading(text, compactHeading);
  }
  const fullHeading = collapseRepeatedTail(stripRoadmapPrefix(heading || ""));
  if (fullHeading && fullHeading !== compactHeading) {
    text = removeTrailingHeading(text, fullHeading);
  }
  return cleanupSeparators(text) || cleanupSeparators(stripRoadmapPrefix(raw)) || compactHeading || "fields-study-flow";
}

export function collapseRepeatedTail(value: string): string {
  let text = normalizeSpaces(value);
  for (let pass = 0; pass < 3; pass += 1) {
    let changed = false;
    for (let size = Math.floor(text.length / 2); size >= 16; size -= 1) {
      const tail = text.slice(text.length - size).trim();
      const prefix = text.slice(0, text.length - size).trim();
      const prefixWithoutSeparator = cleanupSeparators(prefix);
      if (normalizeComparable(prefixWithoutSeparator).endsWith(normalizeComparable(tail))) {
        text = prefixWithoutSeparator;
        changed = true;
        break;
      }
    }
    if (!changed) break;
  }
  return text;
}

function removeTrailingHeading(value: string, heading: string): string {
  const cleanHeading = normalizeSpaces(heading);
  if (cleanHeading.length < 8) return value;
  let text = value;
  const comparableHeading = normalizeComparable(cleanHeading);
  for (let pass = 0; pass < 3; pass += 1) {
    const cleaned = cleanupSeparators(text);
    if (!normalizeComparable(cleaned).endsWith(comparableHeading)) break;
    text = cleanupSeparators(cleaned.slice(0, cleaned.length - cleanHeading.length));
  }
  return text;
}

function stripRoadmapPrefix(value: string): string {
  return normalizeSpaces(value).replace(
    /^(Learning Roadmap(?:\s*\/\s*\u5b66\u4e60\u8def\u7ebf)?|\u5b66\u4e60\u8def\u7ebf)\s*[:\uff1a]\s*/i,
    "",
  );
}

function compactAcademicTitle(value: string): string {
  const text = normalizeSpaces(value);
  const separator = text.indexOf(":");
  if (separator > 5 && separator <= 52) {
    return text.slice(0, separator).trim();
  }
  return text;
}

function cleanupSeparators(value: string): string {
  return normalizeSpaces(value).replace(/[\s:,\-;\uff1a\uff0c\uff1b]+$/u, "").trim();
}

function normalizeSpaces(value: string): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeComparable(value: string): string {
  return normalizeSpaces(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}
