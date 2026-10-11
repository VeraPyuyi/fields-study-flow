import { act, cleanup, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ResearchContext, Roadmap } from "../types";
import { RoadmapApp } from "../RoadmapApp";
import { PaperMapApp } from "../PaperMapApp";
import { adaptResearchContext, allResources } from "./adapter";
import { createStudyState, useStudyState } from "./useStudyState";

afterEach(() => { cleanup(); localStorage.clear(); history.replaceState(null, "", location.pathname); });
function fixture(): ResearchContext {
  return { schema_version: 1, bundle_id: "review-bundle", snapshot_id: "old", sources: [
    { id: "paper", kind: "paper", title: "Paper", fingerprint: "unchanged", local_href: "../../assets/paper.pdf" },
  ], anchors: [
    { id: "a", source_id: "paper", snippet: "First excerpt", locator: { page: 1 }, locator_status: "valid" },
    { id: "b", source_id: "paper", snippet: "Second excerpt", locator: { page: 2 }, locator_status: "valid" },
  ], claims: [
    { id: "claim-a", kind: "methodology", statement: "First statement", anchor_ids: ["a"], evidence_status: "located" },
    { id: "claim-b", kind: "result", statement: "Second statement", anchor_ids: ["b"], evidence_status: "located" },
  ], relations: [], learning_steps: [
    { id: "step-a", title: "Review method", claim_ids: ["claim-a"], anchor_ids: ["a"], task_ids: ["task-1"], prerequisite_ids: [], reason: "Check the method", status: "available" },
  ] };
}
describe("readonly review regressions", () => {
  it("keeps every unbound required task actionable with its own portable answer", () => {
    const context = fixture();
    const tasks = ["explain", "derive", "reproduce", "critique"].map((type, i) => ({ id: `task-${i + 1}`, type, title: `Required ${type}`, acceptance: `Check ${type}` }));
    render(<RoadmapApp roadmap={{ profile: { output_language: "en" }, research_context: context, study_tasks: tasks }} />);
    for (const type of ["derive", "reproduce", "critique"]) {
      fireEvent.click(screen.getByRole("button", { name: `Required ${type}` }));
      expect(screen.getByText(`Check ${type}`)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("tab", { name: "Notes" }));
      fireEvent.change(screen.getByLabelText("My answer"), { target: { value: `My ${type} answer` } });
    }
    const stored = JSON.parse(localStorage.getItem("fields-study-flow:study:v1:review-bundle")!);
    expect(stored.records["task-2"].answer).toBe("My derive answer");
    expect(stored.records["task-3"].answer).toBe("My reproduce answer");
    expect(stored.records["task-4"].answer).toBe("My critique answer");
  });

  it("marks only affected semantic dependencies stale despite identical source fingerprints", () => {
    const original = fixture();
    const first = renderHook(() => useStudyState(original));
    act(() => {
      first.result.current.updateRecord("step-a", { answer: "Method answer" });
      first.result.current.updateRecord("claim-b", { answer: "Result answer" });
    });
    const portable = first.result.current.exportState();
    first.unmount();
    const changed = { ...original, snapshot_id: "new", claims: original.claims.map(c => ({ ...c, statement: c.id === "claim-a" ? "Corrected statement" : c.statement })) };
    const second = renderHook(() => useStudyState(changed));
    expect(second.result.current.state.records["step-a"].stale).toBe(true);
    expect(second.result.current.state.records["claim-b"].stale).toBe(false);
    const depsChanged = { ...original, learning_steps: original.learning_steps.map(s => ({ ...s, anchor_ids: ["b"], claim_ids: ["claim-b"] })) };
    const third = renderHook(() => useStudyState(depsChanged));
    act(() => third.result.current.importState(portable));
    expect(third.result.current.state.records["step-a"].stale).toBe(true);
    expect(third.result.current.state.records["claim-b"].stale).toBe(false);
  });

  it("conservatively marks unexplained snapshot changes stale without deleting answers", () => {
    const original = fixture();
    const first = renderHook(() => useStudyState(original));
    act(() => first.result.current.updateRecord("claim-a", { answer: "Retain this" }));
    const portable = first.result.current.exportState();
    const changed = { ...original, snapshot_id: "unexplained-new-snapshot" };
    act(() => first.result.current.importState(portable));
    first.unmount();
    const next = renderHook(() => useStudyState(changed));
    expect(next.result.current.state.records["claim-a"]).toMatchObject({ stale: true, answer: "Retain this" });
  });

  it("merges library and bundle identities while retaining local materialization and distinct same-title sources", () => {
    const roadmap: Roadmap = { profile: { output_language: "en" }, resource_library: [
      { title: "Same", url: "https://example.org/one", status: "link-only", metadata: { rag: { evidence_chunks: [{ snippet: "Coverage" }] } } },
      { title: "Same", url: "https://example.org/two" },
    ], study_bundle: { resources: [{ title: "Same", url: "https://example.org/one", local_href: "../../assets/one.pdf", status: "downloaded" }] } };
    const resources = allResources(roadmap);
    expect(resources).toHaveLength(2);
    expect(resources[0]).toMatchObject({ local_href: "../../assets/one.pdf", status: "downloaded", metadata: { rag: { evidence_chunks: [{ snippet: "Coverage" }] } } });
    render(<RoadmapApp roadmap={roadmap} />);
    expect(screen.getByRole("link", { name: "Open local" })).toHaveAttribute("href", "../../assets/one.pdf");
    fireEvent.change(screen.getByLabelText("Material status"), { target: { value: "downloaded" } });
    expect(document.querySelectorAll(".resource-item")).toHaveLength(1);
  });

  it("selects the paragraph sharing graph claim anchors, not the first same-kind paragraph", () => {
    const context = fixture();
    context.anchors[0].snippet = "Truncated fragment";
    render(<PaperMapApp roadmap={{ profile: { output_language: "en" }, research_context: context,
      paper_map: { nodes: [{ id: "core-method", kind: "methodology", claim_id: "claim-a", label: "Method" }] },
      paper_lens: { segments: [
        { id: "wrong", section_kind: "methodology", original_text: "Another method paragraph", anchor_ids: ["b"] },
        { id: "right", section_kind: "method", original_text: "Full paragraph that does not equal the truncated fragment", anchor_ids: ["a"] },
      ] } }} />);
    act(() => { location.hash = "core-method"; window.dispatchEvent(new Event("hashchange")); });
    expect(screen.getByRole("link", { name: "Reading" })).toHaveAttribute("href", "paper_lens.html?lang=en#segment-right");
  });

  it("reconciles graph IDs and labels on fresh data without replacing saved coordinates or the canvas", () => {
    const context = fixture();
    const saved = createStudyState(context);
    saved.graph.positions.old = { x: 91, y: 123 };
    localStorage.setItem("fields-study-flow:study:v1:review-bundle", JSON.stringify(saved));
    const roadmap: Roadmap = { profile: { output_language: "en" }, research_context: context,
      paper_map: { nodes: [{ id: "old", kind: "methodology", label: "Old label" }, { id: "removed", kind: "result", label: "Remove me" }] } };
    const view = render(<PaperMapApp roadmap={roadmap} />);
    const canvas = document.querySelector("[data-paper-map-canvas]");
    view.rerender(<PaperMapApp roadmap={{ ...roadmap, paper_map: { nodes: [{ id: "old", kind: "methodology", label: "Fresh label" }, { id: "added", kind: "result", label: "New node" }] } }} />);
    expect(document.querySelector('[data-id="old"] .node-title')).toHaveTextContent("Fresh label");
    expect((document.querySelector('[data-id="old"]') as HTMLElement).style.transform).toBe("translate(91px,123px)");
    expect(document.querySelector('[data-id="removed"]')).toBeNull();
    expect(document.querySelector('[data-id="added"]')).not.toBeNull();
    expect(document.querySelector("[data-paper-map-canvas]")).toBe(canvas);
  });

  it("falls back safely for malformed context arrays and malformed list members", () => {
    for (const field of ["sources", "anchors", "claims", "relations", "learning_steps"]) {
      const roadmap = { title: "Fallback", study_tasks: [{ id: "task", title: "Legacy task" }], research_context: { ...fixture(), [field]: {} } } as Roadmap;
      expect(() => adaptResearchContext(roadmap)).not.toThrow();
      const view = render(<RoadmapApp roadmap={roadmap} />);
      expect(screen.getAllByText("Legacy task").length).toBeGreaterThan(0);
      view.unmount();
    }
    expect(() => adaptResearchContext({ research_context: { ...fixture(), claims: [null] } } as unknown as Roadmap)).not.toThrow();
  });

  it("shows material and prerequisite problems separately from record status and compacts statement titles", () => {
    const context = fixture();
    const statement = "External unabridged research statement with all original qualifications. ".repeat(6);
    context.claims[0].statement = statement;
    context.learning_steps[0] = { ...context.learning_steps[0], title: statement.slice(0, 300), status: "needs_material", prerequisite_ids: ["missing-step", "step-b"] };
    context.learning_steps.push({ ...context.learning_steps[0], id: "step-b", title: "显式自定标题", prerequisite_ids: ["step-a"], claim_ids: ["claim-b"] });
    render(<RoadmapApp roadmap={{ profile: { output_language: "zh-CN", learning_outcome: "understand" }, research_context: context }} />);
    const rail = screen.getByRole("navigation", { name: "学习步骤" });
    expect(within(rail).getAllByText("材料待补").length).toBeGreaterThan(0);
    expect(within(rail).getAllByText("先修步骤缺失").length).toBeGreaterThan(0);
    expect(within(rail).getAllByText("先修关系存在循环").length).toBeGreaterThan(0);
    expect(within(rail).getAllByText("未开始").length).toBe(2);
    expect(rail.textContent).not.toContain("External unabridged");
    expect(within(rail).getByText("显式自定标题")).toBeInTheDocument();
    expect(rail.textContent).toContain("理解方法");
    fireEvent.click(within(rail).getAllByRole("button")[0]);
    expect(within(document.querySelector(".context-panel") as HTMLElement).getByText(statement.trim())).toBeInTheDocument();
  });
});
