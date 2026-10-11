import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PaperLensApp } from "../PaperLensApp";
import { RoadmapApp } from "../RoadmapApp";
import { PaperMapApp } from "../PaperMapApp";
import { linkHref } from "../data";
import { createMapNodes, projectMap, setBranchExpanded } from "./mapState";
import { adaptResearchContext, anchorsForNode, nodeForClaim } from "./adapter";
import { WorkbenchProvider } from "./WorkbenchProvider";
import { ContextPanel } from "./ContextPanel";
import type { Roadmap } from "../types";

afterEach(() => { cleanup(); localStorage.clear(); history.replaceState(null, "", location.pathname); vi.restoreAllMocks(); });

const legacy: Roadmap = {
  title: "Test paper", profile: { output_language: "en" },
  paper_map: { nodes: [
    { id: "method", kind: "methodology", label: "Method", plain_explanation: "Full explanation" },
    { id: "resource", kind: "resource", label: "Code" },
  ], edges: [{ from: "method", to: "resource" }] },
  paper_lens: { segments: [
    { id: "one", original_text: "First full paragraph.", section_title: "Methods", section_kind: "methodology" },
    { id: "two", original_text: "Second full paragraph.", section_title: "Results", section_kind: "result" },
  ], inline_explanations: [{ segment_id: "two", plain_meaning: "Selected second explanation" }] },
  study_tasks: [{ id: "explain", title: "Explain it", type: "explain" }],
};

describe("workbench behavior", () => {
  it("links a step's source once even when several excerpts cite it", () => {
    const context = adaptResearchContext(legacy);
    context.sources = [{ id: "paper", kind: "paper", title: "Source", fingerprint: "v1", local_href: "study-assets/note.md" }];
    context.anchors = ["a", "b"].map(id => ({ id, source_id: "paper", locator: { page: 1 }, locator_status: "valid", snippet: id }));
    context.learning_steps[0].anchor_ids = ["a", "b"];
    render(<RoadmapApp roadmap={{ ...legacy, research_context: context }} />);
    expect(document.querySelectorAll('.step-overview a[href="study-assets/note.md"]')).toHaveLength(1);
  });

  it("retains dragged coordinates and stable IDs across twenty parent branch toggles", () => {
    const edges = legacy.paper_map!.edges!;
    const nodes = createMapNodes(legacy.paper_map!.nodes!);
    nodes[0].position = { x: 91, y: 123 };
    let expanded: string[] = [];
    for (let i = 0; i < 20; i++) {
      expanded = setBranchExpanded(expanded, "method", !expanded.includes("method"));
      const projection = projectMap(nodes, edges, expanded, "method");
      expect(projection.nodes.map(n => n.id)).toEqual(["method", "resource"]);
      expect(projection.nodes[0].position).toEqual({ x: 91, y: 123 });
      expect(projection.nodes[1].hidden).toBe(!expanded.includes("method"));
      expect(projection.edges[0].hidden).toBe(projection.nodes[1].hidden);
    }
  });

  it("adapts old data without claiming scientific verification", () => {
    const context = adaptResearchContext(legacy);
    expect(context.learning_steps[0].task_ids).toEqual(["explain"]);
    expect(context.claims[0].evidence_status).toBe("unverified");
  });

  it("uses local links first and rejects active or unresolved links", () => {
    expect(linkHref({ local_href: "bundle/paper.pdf", url: "https://example.org" })).toBe("bundle/paper.pdf");
    expect(linkHref({ local_href: "local://unresolved", url: "https://example.org" })).toBe("https://example.org");
    expect(linkHref({ href: "javascript:alert(1)" })).toBe("");
    expect(linkHref({ href: "data:text/html,evil" })).toBe("");
  });

  it("honors profile language and explicit page language", () => {
    const view = render(<RoadmapApp roadmap={legacy} />);
    expect(screen.getByRole("link", { name: "Graph" })).toBeInTheDocument();
    view.unmount();
    history.replaceState(null, "", "?lang=zh-CN");
    render(<RoadmapApp roadmap={legacy} />);
    expect(screen.getByRole("link", { name: "逻辑图" })).toBeInTheDocument();
  });

  it("keeps paragraph text outside buttons and follows incoming hash changes", () => {
    history.replaceState(null, "", "#segment-two");
    render(<PaperLensApp roadmap={legacy} />);
    const text = screen.getByText("Second full paragraph.");
    expect(text.tagName).toBe("P");
    expect(text.closest("button")).toBeNull();
    expect(screen.getByText("Selected second explanation")).toBeInTheDocument();
    act(() => { location.hash = "segment-one"; window.dispatchEvent(new Event("hashchange")); });
    expect(screen.getByRole("button", { name: "Select paragraph 1" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Select paragraph 2" }));
    expect(location.hash).toBe("#segment-two");
  });

  it("translates accepted and rejected relationships and structured locators", () => {
    const context = adaptResearchContext(legacy);
    context.claims[0].anchor_ids = ["a"];
    context.sources = [{ id: "s", kind: "paper", title: "Paper", fingerprint: "v1", local_href: "../../study-assets/paper.pdf" }];
    context.anchors = [{ id: "a", source_id: "s", snippet: "Excerpt", locator: { page: 3, cell_id: "c", row: 2, column: "x", line_start: 10 }, locator_status: "valid" }];
    context.relations = [
      { id: "r", from: "method", to: "s", kind: "supports", origin: "human", review_status: "accepted", anchor_ids: ["a"] },
      { id: "r2", from: "method", to: "s", kind: "implements", origin: "rule", review_status: "rejected", anchor_ids: [] },
    ];
    render(<WorkbenchProvider roadmap={{ ...legacy, profile: { output_language: "zh-CN" }, research_context: context }}><ContextPanel claimId="method" /></WorkbenchProvider>);
    expect(screen.getByText("已接受关系")).toBeInTheDocument();
    expect(screen.getByText("已拒绝关系")).toBeInTheDocument();
    expect(screen.getByText("人工标注")).toBeInTheDocument();
    expect(screen.getByText("规则匹配")).toBeInTheDocument();
    expect(screen.getByText(/页 3.*行 10.*单元格 c.*数据行 2.*列 x/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开本地" })).toHaveAttribute("href", "../../study-assets/paper.pdf#page=3");
    expect(screen.getByText("来源已定位")).toBeInTheDocument();
    expect(screen.getByText("科学含义待核对")).toBeInTheDocument();
  });

  it("links learning claims to actual core IDs and resolves incoming claim deep links", () => {
    const context = adaptResearchContext(legacy);
    context.claims = [{ id: "claim-one", kind: "methodology", statement: "Full claim one", anchor_ids: ["a"], evidence_status: "located" },
      { id: "claim-two", kind: "methodology", statement: "Full claim two", anchor_ids: ["b"], evidence_status: "partial" }];
    context.learning_steps[0].claim_ids = ["claim-two"];
    const node = { id: "core-methodology", label: "Grouped method", kind: "methodology", claim_id: "claim-one", claim_ids: ["claim-one", "claim-two"], anchor_ids: ["c"] };
    const roadmap = { ...legacy, research_context: context, paper_map: { nodes: [node], edges: [] } };
    expect(anchorsForNode(context, node)).toEqual(["c", "a", "b"]);
    expect(nodeForClaim([node], context, "claim-two")?.id).toBe("core-methodology");
    const view = render(<RoadmapApp roadmap={roadmap} />);
    fireEvent.click(within(screen.getByRole("navigation", { name: "Learning steps" })).getByRole("button", { name: /1 Explain it Not started/ }));
    const link = within(document.querySelector(".page-tabs") as HTMLElement).getByRole("link", { name: "Graph" });
    expect(link.getAttribute("href")).toBe("paper_map.html?lang=en#core-methodology");
    const href = link.getAttribute("href")!;
    link.addEventListener("click", e => e.preventDefault());
    fireEvent.click(link);
    view.unmount();
    history.replaceState(null, "", href);
    render(<PaperMapApp roadmap={roadmap} />);
    expect(screen.getByRole("heading", { name: "Grouped method" })).toBeInTheDocument();
    expect(screen.getByText("Full claim one")).toBeInTheDocument();
  });

  it("normalizes answer_questions and keeps resource dimensions available and opt-in", () => {
    const context = adaptResearchContext(legacy);
    context.learning_steps[0].answer_questions = ["What assumption is necessary?"];
    const roadmap = { ...legacy, research_context: context, resource_library: [
      { title: "Code copy", type: "repository", source: "github", status: "copied", selected: false, local_href: "../../study-assets/code.py" },
      { title: "Generated exercise", type: "notebook", source: "local", status: "generated", selected: true, local_href: "exercise.ipynb" },
    ] };
    render(<RoadmapApp roadmap={roadmap} />);
    expect(screen.getByText("What assumption is necessary?")).toBeInTheDocument();
    expect(screen.getByLabelText("Current step resources")).not.toBeChecked();
    const library = document.getElementById("resource-library")!;
    expect(library.textContent).toContain("Code copy");
    expect(library.textContent).toContain("Generated exercise");
    fireEvent.change(screen.getByLabelText("Material status"), { target: { value: "copied" } });
    expect(library.textContent).toContain("Code copy");
    expect(library.querySelector(".resource-list")!.textContent).not.toContain("Generated exercise");
    expect(screen.getByLabelText("Resource type")).toBeInTheDocument();
    expect(screen.getByLabelText("Resource source")).toBeInTheDocument();
    expect(screen.getByLabelText("Route status")).toBeInTheDocument();
  });

  it("reports actual coverage caps but not mere configured limits", () => {
    const context = adaptResearchContext(legacy);
    context.coverage = { limits: { max_files: 10 }, input_analysis: [{ files_inspected: 2, max_files: 10, limit_reached: false }] };
    const view = render(<RoadmapApp roadmap={{ ...legacy, research_context: context }} />);
    expect(screen.queryByText("Some material was excluded by parsing limits")).not.toBeInTheDocument();
    view.unmount();
    context.coverage.input_analysis![0].limit_reached = true;
    render(<RoadmapApp roadmap={{ ...legacy, research_context: context }} />);
    expect(screen.getByText("Some material was excluded by parsing limits")).toBeInTheDocument();
  });

  it("binds truncated paragraph anchors to their actual claim and leaves unbound paragraphs missing", () => {
    const context = adaptResearchContext(legacy);
    const full = "A long methodology paragraph. ".repeat(20);
    context.sources = [{ id: "source", kind: "paper", title: "Source PDF", fingerprint: "v1", local_href: "../../study-assets/paper.pdf" }];
    context.anchors = [{ id: "paragraph-anchor", source_id: "source", snippet: full.slice(0, 300), locator: { page: 5 }, locator_status: "valid" }];
    context.claims = [
      { id: "unrelated-method", kind: "methodology", statement: "Unrelated claim must not appear", anchor_ids: [], evidence_status: "missing" },
      { id: "actual-method", kind: "methodology", statement: "Correct anchored claim", anchor_ids: ["paragraph-anchor"], evidence_status: "located" },
    ];
    const roadmap: Roadmap = { profile: { output_language: "en" }, research_context: context, paper_lens: { segments: [
      { id: "paragraph", section_kind: "method", original_text: full, anchor_ids: ["paragraph-anchor"] },
      { id: "missing-paragraph", section_kind: "unknown", original_text: "No supplied evidence here.", anchor_ids: [] },
    ] } };
    render(<PaperLensApp roadmap={roadmap} />);
    expect(screen.getByText("Correct anchored claim")).toBeInTheDocument();
    expect(screen.getByText(full.slice(0, 300).trim())).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open local" })).toHaveAttribute("href", "../../study-assets/paper.pdf#page=5");
    expect(screen.queryByText("Unrelated claim must not appear")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select paragraph 2" }));
    expect(screen.getByText("Material missing")).toBeInTheDocument();
    expect(screen.queryByText("Correct anchored claim")).not.toBeInTheDocument();
    expect(screen.queryByText(full.slice(0, 300).trim())).not.toBeInTheDocument();
  });

  it("omits disabled report links and changes interface labels without translating saved explanations", () => {
    render(<PaperLensApp roadmap={{ ...legacy, paper_map_disabled: true, paper_lens_disabled: true }} />);
    expect(document.querySelector('a[href^="paper_map.html"]')).toBeNull();
    expect(document.querySelector('a[href^="paper_lens.html"]')).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Select paragraph 2" }));
    expect(screen.getByText("Selected second explanation")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Interface language"), { target: { value: "zh-CN" } });
    expect(screen.getByRole("button", { name: "选择段落 2" })).toBeInTheDocument();
    expect(screen.getByText("Selected second explanation")).toBeInTheDocument();
  });
});
