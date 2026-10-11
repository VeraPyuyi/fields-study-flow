import { useEffect, useRef, useState, type ReactNode } from "react";
import { BookOpen, Download, GitFork, ListChecks, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Upload, X } from "lucide-react";
import { Group, Panel, Separator, usePanelRef } from "react-resizable-panels";
import type { ReportKind } from "../types";
import { targetPaperTitle, reportHeadingTitle } from "../data";
import { useWorkbench } from "./WorkbenchProvider";
import { LearningRail } from "./LearningRail";
import type { Language } from "./messages";

export function useNarrowViewport(query = "(max-width: 1279px)") {
  const [match, setMatch] = useState(() => typeof matchMedia === "function" && matchMedia(query).matches);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const media = matchMedia(query);
    const update = () => setMatch(media.matches);
    media.addEventListener("change", update);
    update();
    return () => media.removeEventListener("change", update);
  }, [query]);
  return match;
}
export function IconButton({ label, children, onClick, pressed }: { label: string; children: ReactNode; onClick: () => void; pressed?: boolean }) {
  return <button type="button" className="icon-button" title={label} aria-label={label} aria-pressed={pressed} onClick={onClick}>{children}</button>;
}

export function WorkbenchLayout({ page, children, context, actions }: { page: ReportKind; children: ReactNode; context: ReactNode; actions?: ReactNode }) {
  const { roadmap, context: research, study, t, language, setLanguage, pageHref, contextRequest } = useWorkbench();
  const narrow = useNarrowViewport();
  const left = usePanelRef();
  const right = usePanelRef();
  const [leftOpen, setLeftOpen] = useState(!narrow);
  const [rightOpen, setRightOpen] = useState(!narrow);
  const [drawer, setDrawer] = useState<"left" | "right" | null>(null);
  const [notice, setNotice] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const previousNarrow = useRef(narrow);
  const layoutKey = `fields-study-flow:panels:${roadmap.research_context?.bundle_id || "legacy"}`;
  const [savedLayout] = useState(() => { try { const value = JSON.parse(localStorage.getItem(layoutKey) || "null");
    return value && typeof value.left === "number" && typeof value.right === "number" && typeof value.center === "number" ? value as Record<string, number> : undefined;
  } catch { return undefined; } });
  useEffect(() => {
    if (narrow) { left.current?.collapse(); right.current?.collapse(); }
    else if (previousNarrow.current) { left.current?.expand(); right.current?.expand(); setDrawer(null); }
    previousNarrow.current = narrow;
  }, [narrow, left, right]);
  useEffect(() => {
    if (!contextRequest) return;
    if (narrow) setDrawer("right"); else right.current?.expand();
  }, [contextRequest, narrow, right]);
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (drawer && !node.open) {
      if (typeof node.showModal === "function") node.showModal(); else node.setAttribute("open", "");
    } else if (!drawer && node.open) {
      if (typeof node.close === "function") node.close(); else node.removeAttribute("open");
    }
  }, [drawer]);
  function toggleRail(side: "left" | "right") {
    if (narrow) { setDrawer(drawer === side ? null : side); return; }
    const panel = side === "left" ? left.current : right.current;
    if (panel?.isCollapsed()) panel.expand(); else panel?.collapse();
  }
  async function importFile(file?: File) {
    if (!file) return;
    try { if (file.size > 10_000_000) throw new Error("Too large"); study.importState(await file.text()); setNotice(t("imported")); }
    catch { setNotice(t("importFailed")); }
    if (input.current) input.current.value = "";
  }
  function exportFile() {
    try {
      const url = URL.createObjectURL(new Blob([study.exportState()], { type: "application/json" }));
      const a = document.createElement("a"); a.href = url; a.download = "study_state.json"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setNotice(t("exportFailed")); }
  }
  const title = reportHeadingTitle(roadmap, targetPaperTitle(roadmap) || roadmap.title || "Study Flow");
  const coverage = research.coverage;
  const limited = coverage?.truncated === true || (Array.isArray(coverage?.truncated) && coverage.truncated.length > 0) || coverage?.input_analysis?.some(a => a.limit_reached)
    || coverage?.skipped?.some(s => /limit|truncat|cap/i.test(s.reason || ""));
  return <main className="workbench" lang={language === "en" ? "en" : "zh-CN"}>
    <header className="workbench-header">
      <div className="header-top"><span className="wordmark">Study Flow</span><h1 title={targetPaperTitle(roadmap) || title}>{title}</h1>
        <div className="header-tools">
          {study.temporary && <span className="session-badge" title={t("temporary")}>{t("temporary")}</span>}
          <select aria-label={t("language")} value={language} onChange={e => setLanguage(e.target.value as Language)}><option value="zh-CN">中文</option><option value="en">English</option><option value="bilingual">双语</option></select>
          <IconButton label={t("import")} onClick={() => input.current?.click()}><Upload size={17} /></IconButton>
          <IconButton label={t("export")} onClick={exportFile}><Download size={17} /></IconButton>
          <input ref={input} type="file" accept=".json,application/json" hidden onChange={e => void importFile(e.target.files?.[0])} />
        </div>
      </div>
      <div className="header-bottom">
        <IconButton label={leftOpen && !narrow ? t("closeSteps") : t("openSteps")} onClick={() => toggleRail("left")} pressed={narrow ? drawer === "left" : leftOpen}>{leftOpen && !narrow ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}</IconButton>
        <nav className="page-tabs">{([
          ["paper_map", "paper_map.html", "graph", GitFork], ["paper_lens", "paper_lens.html", "reading", BookOpen], ["roadmap", "roadmap.html", "learning", ListChecks],
        ] as const).filter(([kind]) => kind === "roadmap" || !roadmap[`${kind}_disabled`]).map(([kind, file, key, Icon]) => <a key={kind} aria-current={page === kind ? "page" : undefined} href={pageHref(file, kind === "paper_map" ? study.state.selection.claimId : kind === "paper_lens" && study.state.selection.segmentId ? `segment-${study.state.selection.segmentId}` : kind === "roadmap" ? study.state.selection.stepId : "")}><Icon size={16} />{t(key)}</a>)}</nav>
        <div className="page-actions">{actions}</div>
        <IconButton label={rightOpen && !narrow ? t("closeContext") : t("openContext")} onClick={() => toggleRail("right")} pressed={narrow ? drawer === "right" : rightOpen}>{rightOpen && !narrow ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}</IconButton>
      </div>
    </header>
    {limited && <div className="coverage-notice warning" role="status">{t("coverageLimit")}</div>}
    {notice && <div className="notice" role="status">{notice}<IconButton label={t("close")} onClick={() => setNotice("")}><X size={14} /></IconButton></div>}
    <Group id="research-workspace" className="workspace-group" orientation="horizontal" defaultLayout={narrow ? undefined : savedLayout}
      onLayoutChanged={layout => { if (!narrow) try { localStorage.setItem(layoutKey, JSON.stringify(layout)); } catch { /* Panels still resize in temporary sessions. */ } }}>
      <Panel id="left" panelRef={left} defaultSize={narrow ? "0px" : "224px"} minSize="180px" maxSize="320px" collapsedSize="0px" collapsible onResize={size => setLeftOpen(size.asPercentage > 0)}>
        <div className="rail-scroll"><LearningRail /></div>
      </Panel>
      <Separator className={`resize-separator ${!leftOpen ? "collapsed" : ""}`} aria-label={t("resize")} />
      <Panel id="center" minSize={narrow ? "100%" : "360px"}><div className="center-surface">{children}</div></Panel>
      <Separator className={`resize-separator ${!rightOpen ? "collapsed" : ""}`} aria-label={t("resize")} />
      <Panel id="right" panelRef={right} defaultSize={narrow ? "0px" : "360px"} minSize="280px" maxSize="560px" collapsedSize="0px" collapsible onResize={size => setRightOpen(size.asPercentage > 0)}>
        <aside className="context-rail rail-scroll" aria-label={t("context")}>{context}</aside>
      </Panel>
    </Group>
    <dialog ref={dialog} className={`rail-drawer ${drawer === "left" ? "drawer-left" : ""}`} aria-label={drawer === "left" ? t("steps") : t("context")}
      onCancel={() => setDrawer(null)} onClick={e => { if (e.target === e.currentTarget) setDrawer(null); }}>
      <div className="drawer-header"><h2>{drawer === "left" ? t("steps") : t("context")}</h2><IconButton label={t("close")} onClick={() => setDrawer(null)}><X size={18} /></IconButton></div>
      <div className="drawer-body">{drawer === "left" ? <LearningRail /> : drawer === "right" ? context : null}</div>
    </dialog>
  </main>;
}
