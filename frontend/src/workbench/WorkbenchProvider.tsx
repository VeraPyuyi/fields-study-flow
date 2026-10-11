import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Roadmap } from "../types";
import { adaptResearchContext, graphData, nodeForClaim } from "./adapter";
import { resolveLanguage, translate, type Language, type MessageKey } from "./messages";
import { useStudyState } from "./useStudyState";

function useWorkbenchValue(roadmap: Roadmap) {
  const context = useMemo(() => adaptResearchContext(roadmap), [roadmap]);
  const segments = useMemo(() => roadmap.paper_lens?.segments || [], [roadmap.paper_lens?.segments]);
  const tasks = useMemo(() => roadmap.study_tasks || [], [roadmap.study_tasks]);
  const study = useStudyState(context, segments, tasks);
  const [contextRequest, requestContext] = useState(0);
  const showContext = useCallback(() => requestContext(v => v + 1), []);
  const [language, setLanguage] = useState<Language>(() => resolveLanguage(roadmap.profile?.output_language,
    new URLSearchParams(location.search).get("lang") || roadmap.page_language));
  function pageHref(file: string, hash = "") {
    const target = file === "paper_map.html" ? nodeForClaim(graphData(roadmap, context).nodes, context, hash)?.id || hash : hash;
    return `${file}?lang=${encodeURIComponent(language)}${target ? `#${encodeURIComponent(target)}` : ""}`;
  }
  return { roadmap, context, study, language, setLanguage, pageHref, contextRequest,
    showContext, t: (key: MessageKey) => translate(language, key) };
}
const WorkbenchContext = createContext<ReturnType<typeof useWorkbenchValue> | null>(null);
export function WorkbenchProvider({ roadmap, children }: { roadmap: Roadmap; children: ReactNode }) {
  const value = useWorkbenchValue(roadmap);
  return <WorkbenchContext.Provider value={value}>{children}</WorkbenchContext.Provider>;
}
export function useWorkbench() {
  const value = useContext(WorkbenchContext);
  if (!value) throw new Error("Workbench provider required");
  return value;
}
