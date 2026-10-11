import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { vi } from "vitest";
import { App } from "./App";
import stylesCss from "./styles.css?raw";
import type { Roadmap } from "./types";
import { createMapNodes, projectMap } from "./workbench/mapState";

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

function installPayload(payload: unknown) {
  document.body.innerHTML = '<div id="root"></div><script type="application/json" id="fields-study-flow-data"></script>';
  const script = document.getElementById("fields-study-flow-data");
  if (script) script.textContent = JSON.stringify(payload);
}

afterEach(() => {
  cleanup();
  history.replaceState(null, "", location.pathname);
  document.body.innerHTML = "";
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("fields-study-flow React report app", () => {
  it("does not clip Paper Map node text with fixed-height hidden overflow", () => {
    expect(stylesCss).not.toMatch(/\.map-node\s*\{[^}]*\bmax-height\s*:/s);
    expect(stylesCss).not.toMatch(/\.map-node\s*\{[^}]*\boverflow\s*:\s*hidden\b/s);
    expect(stylesCss).not.toMatch(/\.map-node strong\s*\{[^}]*\bmax-height\s*:/s);
    expect(stylesCss).not.toMatch(/\.map-node strong\s*\{[^}]*\boverflow\s*:\s*hidden\b/s);
    expect(stylesCss).not.toMatch(/\.map-node p\s*\{[^}]*\bmax-height\s*:/s);
    expect(stylesCss).not.toMatch(/\.map-node p\s*\{[^}]*\boverflow\s*:\s*hidden\b/s);
  });

  it("keeps long report text intact instead of inserting visible ellipses", () => {
    const longPaperTitle =
      "Teaching LLMs to Plan Logical Chain-of-Thought Instruction Tuning for Symbolic Planning with Detailed Evidence Coverage";
    const longNodeText =
      "This node explains how background motivation problem methodology experiments contributions and limitations connect into one readable paper map";
    installPayload({
      reportKind: "paper_map",
      roadmap: {
        title: longPaperTitle,
        profile: { goal: longPaperTitle, output_language: "zh-CN" },
        paper_map: {
          target: { title: longPaperTitle },
          nodes: [
            {
              id: "target",
              role: "target",
              kind: "target",
              label: longPaperTitle,
              plain_explanation: longNodeText,
              evidence: [{ resource_title: "Target PDF", snippet: "Evidence coverage" }],
            },
          ],
          edges: [],
        },
      },
    });

    render(<App />);

    expect(document.body.textContent).toContain("Detailed Evidence Coverage");
    expect(document.body.textContent).toContain("readable paper map");
    expect(document.body.textContent).not.toContain("...");
    expect(document.body.textContent).not.toContain("…");
  });

  it("renders learning tasks, local resources and portable private records from embedded JSON", async () => {
    const createObjectURL = vi.fn((_blob: Blob) => "blob:mastery-worksheet");
    const revokeObjectURL = vi.fn();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectURL,
    });

    installPayload({
      reportKind: "roadmap",
      roadmap: {
        title: "Transformer 学习路线",
        profile: { goal: "掌握 Transformer", output_language: "zh-CN" },
        path_strategy: { estimated_total_time: "3h", mode: "fastest" },
        paper_map: { nodes: [{ id: "target", label: "Transformer" }], edges: [] },
        paper_lens: { segments: [{ id: "seg-1", original_text: "Attention is all you need." }] },
        phases: [{ name: "阶段 1", objective: "理解注意力机制", estimated_time: "1h" }],
        study_tasks: [
          {
            id: "task-explain",
            type: "explain",
            title: "解释核心问题",
            evidence: "不看笔记讲清论文问题。",
            acceptance: "别人能听懂问题和贡献。",
            estimated_minutes: 20,
            resource_titles: ["Local PDF"],
          },
          {
            id: "task-derive",
            type: "derive",
            title: "推导关键机制",
            evidence: "用自己的话拆解公式或机制。",
            acceptance: "能说明每一步为什么成立。",
            estimated_minutes: 30,
            evidence_chunks: [{}],
          },
          {
            id: "task-reproduce",
            type: "reproduce",
            title: "复现最小实验",
            evidence: "留下命令输出或 notebook 结果。",
            acceptance: "有可复查结果。",
            estimated_minutes: 60,
            resource_titles: ["Copied Notebook"],
          },
        ],
        study_bundle: {
          readme_file: "README.md",
          readme_href: "../study-assets/README.md",
          links_file: "links.md",
          links_href: "../study-assets/links.md",
          retry_href: "../study-assets/retry_failed.md",
          download_queue_href: "../study-assets/download_queue.json",
          download_manager: { retry_file: "retry_failed.md", download_queue_file: "download_queue.json" },
          summary: { total: 4, completed: 2, downloaded: 1, copied: 1, failed: 1, "link-only": 1 },
          resources: [
            {
              title: "Local PDF",
              local_href: "../assets/a.pdf",
              type: "paper",
              status: "downloaded",
              metadata: { rag: { evidence_chunks: [{ snippet: "Explains the main claim.", file_name: "a.pdf" }] } },
            },
            {
              title: "Copied Notebook",
              local_href: "../assets/b.ipynb",
              type: "notebook",
              status: "copied",
              metadata: { rag: { evidence_chunks: [{ snippet: "Shows a minimal reproduction.", file_name: "b.ipynb" }] } },
            },
            { title: "Broken Repo", url: "https://example.com/repo", type: "repository", status: "failed" },
            { title: "Manual Link", url: "https://example.com/book", type: "book", status: "link-only" },
          ],
        },
      },
    });

    render(<App />);

    const library = document.querySelector("#resource-library") as HTMLElement;
    expect(screen.getByRole("link", { name: "逻辑图" })).toHaveAttribute("href", "paper_map.html?lang=zh-CN");
    expect(screen.getByRole("link", { name: "学习" })).toHaveAttribute("aria-current", "page");
    expect(document.querySelector("[data-roadmap-mastery-readiness]")).toBeNull();
    expect(document.querySelector("[data-roadmap-worksheet-sync]")).toBeNull();
    expect(screen.getByRole("link", { name: "资料包说明", hidden: true })).toHaveAttribute("href", "../study-assets/README.md");
    expect(screen.getByRole("link", { name: "重试清单", hidden: true })).toHaveAttribute("href", "../study-assets/retry_failed.md");
    expect(screen.getByRole("link", { name: "下载队列", hidden: true })).toHaveAttribute("href", "../study-assets/download_queue.json");
    expect(within(library).getByText("Local PDF")).toBeInTheDocument();
    expect(within(library).getAllByRole("link", { name: "打开本地" }).map(a => a.getAttribute("href"))).toEqual(["../assets/a.pdf", "../assets/b.ipynb"]);
    expect(screen.getByLabelText("当前步骤资料")).not.toBeChecked();

    fireEvent.click(within(library).getByRole("button", { name: "下载失败" }));
    expect(within(library).getByText("Broken Repo")).toBeInTheDocument();
    expect(within(library).queryByText("Local PDF")).not.toBeInTheDocument();
    fireEvent.click(within(library).getByRole("button", { name: "全部" }));
    fireEvent.change(screen.getByLabelText("搜索资料"), { target: { value: "notebook" } });
    expect(within(library).getByText("Copied Notebook")).toBeInTheDocument();
    expect(within(library).queryByText("Manual Link")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "记录" }));
    fireEvent.change(screen.getByLabelText("我的回答"), { target: { value: "注意力以查询和键计算权重。" } });
    fireEvent.change(screen.getByLabelText("笔记"), { target: { value: "仍需检查缩放项。" } });
    fireEvent.change(screen.getByLabelText("记录状态"), { target: { value: "self_checked" } });
    expect(screen.queryByText("完全掌握")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "导出学习记录" }));
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    const exported = JSON.parse(await readBlob(createObjectURL.mock.calls[0][0]));
    expect(exported.schema_version).toBe(1);
    expect(exported.records["task-explain"]).toMatchObject({ answer: "注意力以查询和键计算权重。", notes: "仍需检查缩放项。", status: "self_checked" });
    expect(exported.bundle_id).toBeTruthy();
    expect(exported.source_fingerprints).toBeTruthy();
    expect(exported.graph).toMatchObject({ positions: {}, expanded: [] });
    expect(anchorClick).toHaveBeenCalled();
    expect((anchorClick.mock.contexts[0] as HTMLAnchorElement).download).toBe("study_state.json");
    expect(JSON.stringify(exported)).not.toContain("D:\\\\");
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([JSON.stringify(exported)], "study_state.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: () => Promise.resolve(JSON.stringify(exported)) });
    fireEvent.change(screen.getByLabelText("我的回答"), { target: { value: "Temporary edit" } });
    await act(async () => fireEvent.change(input, { target: { files: [file] } }));
    expect(screen.getByText("学习记录已导入")).toBeInTheDocument();
    expect(screen.getByLabelText("我的回答")).toHaveValue("注意力以查询和键计算权重。");
  });

  it("keeps empty reports readable without invented readiness or material", () => {
    installPayload({
      reportKind: "roadmap",
      roadmap: {
        title: "Sparse route",
        profile: { goal: "Learn sparse topic", output_language: "zh-CN" },
        phases: [],
        study_tasks: [],
        study_bundle: { summary: { total: 0 }, resources: [] },
      },
    });

    render(<App />);

    expect(screen.getByRole("heading", { name: "Sparse route" })).toBeInTheDocument();
    expect(screen.getAllByText("暂无学习步骤").length).toBeGreaterThan(0);
    expect(screen.getByText("暂无可打开资料")).toBeInTheDocument();
    expect(screen.getByText("材料待补")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "逻辑图" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导出学习记录" })).toBeEnabled();
    expect(document.querySelector("[data-roadmap-mastery-readiness]")).toBeNull();
    expect(document.querySelector('[data-roadmap-mastery-status="ready"]')).toBeNull();
  });

  it("renders full selectable paragraphs with a separate explanation selection", () => {
    installPayload({
      reportKind: "paper_lens",
      roadmap: {
        title: "Planning Paper",
        profile: { output_language: "zh-CN" },
        paper_lens: {
          target: { title: "Planning Paper" },
          explanation_summary: { granularity: "paragraph" },
          sections: [{ kind: "method", title: "方法" }],
          segments: [
            {
              id: "seg-1",
              section_kind: "method",
              section_title: "方法",
              unit: "paragraph",
              paragraph_index: 1,
              sentence_count: 3,
              original_text: "This paragraph explains how logical traces check preconditions, apply effects, and update states.",
            },
          ],
          inline_explanations: [
            {
              segment_id: "seg-1",
              plain_meaning: "这段把方法讲成一个可检查的状态更新过程。",
              why_it_matters: "它解释了为什么规划不是随便生成文本。",
              method_note: "先看前提，再应用效果，最后检查新状态。",
              confidence: 0.78,
            },
          ],
        },
      },
    });

    render(<App />);

    const paragraph = screen.getByText("This paragraph explains how logical traces check preconditions, apply effects, and update states.");
    expect(paragraph.tagName).toBe("P");
    expect(paragraph.closest("button")).toBeNull();
    const selector = screen.getByRole("button", { name: "选择段落 1" });
    fireEvent.click(selector);
    expect(selector).toHaveAttribute("aria-pressed", "true");
    expect(location.hash).toBe("#segment-seg-1");
    expect(screen.getAllByText("这段把方法讲成一个可检查的状态更新过程。")).toHaveLength(1);
    expect(screen.getByText("先看前提，再应用效果，最后检查新状态。")).toBeInTheDocument();
    expect(screen.getByText("材料待补")).toBeInTheDocument();
    expect(screen.queryByText("段落解释支撑度")).not.toBeInTheDocument();
    expect(screen.queryByText("中（0.78）")).not.toBeInTheDocument();
  });

  it("keeps resource provenance and legacy evidence searchable without promoting scores to verification", () => {
    installPayload({
      reportKind: "roadmap",
      roadmap: {
        title: "Resource badge route",
        profile: { goal: "Understand one paper", output_language: "zh-CN" },
        study_bundle: {
          resources: [
            {
              title: "Target Paper PDF",
              local_href: "assets/paper.pdf",
              source: "arxiv",
              type: "paper",
              status: "downloaded",
              trust_score: 0.96,
              score: 0.91,
              concepts: ["PDDL action preconditions"],
              focus_areas: ["methodology", "experiment"],
              metadata: { target_paper: true },
              why_recommended: "Target paper for claims and experiments.",
            },
            {
              title: "Reference Implementation",
              local_href: "assets/code.zip",
              source: "github",
              type: "repository",
              status: "copied",
              trust_score: 0.81,
              score: 0.78,
              why_recommended: "Implementation support for reproduction.",
            },
            { title: "Planning Background", url: "https://example.com/book", type: "book", status: "link-only" },
            { title: "Weak Related Paper", url: "https://example.com/weak-paper", type: "paper", status: "link-only" },
            { title: "Validation Checklist", local_href: "artifact_template/task_checklist.md", type: "template", status: "generated" },
          ],
        },
        paper_map: {
          nodes: [
            { id: "background", kind: "background", label: "Planning background" },
            { id: "methodology", kind: "methodology", label: "Logical CoT methodology" },
            { id: "experiment", kind: "experiment", label: "PlanBench experiment" },
          ],
          edges: [],
        },
        resource_library: [
          {
            title: "Target Paper PDF",
            metadata: {
              rag: {
                evidence_score: 2.5,
                evidence_chunks: [
                  {
                    snippet: "PDDL preconditions and VAL validation directly support the planning evidence.",
                    score: 2.5,
                    detail_anchor: "detail-seg-pddl-validation",
                  },
                ],
              },
            },
          },
        ],
      },
    });

    render(<App />);

    const library = document.querySelector("#resource-library") as HTMLElement;
    expect(within(library).getByText("Reference Implementation")).toBeInTheDocument();
    const localLinks = within(library).getAllByRole("link", { name: "打开本地" }).map(a => a.getAttribute("href"));
    expect(localLinks).toContain("assets/paper.pdf");
    expect(localLinks).toContain("assets/code.zip");
    expect(localLinks).toContain("artifact_template/task_checklist.md");
    expect(within(library).getByText("Target paper for claims and experiments.")).toBeInTheDocument();
    expect(within(library).getByText(/PDDL preconditions and VAL validation directly/)).toBeInTheDocument();
    expect(within(library).queryByText(/证据强度：高/)).not.toBeInTheDocument();
    expect(within(library).queryByText(/可信分/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("搜索资料"), { target: { value: "VAL validation" } });
    expect(within(library).getByText("Target Paper PDF")).toBeInTheDocument();
    expect(within(library).queryByText("Reference Implementation")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("搜索资料"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("资料类型"), { target: { value: "repository" } });
    expect(within(library).getByText("Reference Implementation")).toBeInTheDocument();
    expect(within(library).queryByText("Planning Background")).not.toBeInTheDocument();
  });

  it("keeps paper-set reading order, comparison and synthesis available on demand", () => {
    installPayload({
      reportKind: "roadmap",
      roadmap: {
        title: "Diffusion paper set",
        profile: { goal: "compare diffusion papers", output_language: "en" },
        paper_set: {
          mode: "paper-set",
          summary: { paper_count: 3, selected_paper_count: 2, shared_concept_count: 1 },
          papers: [
            { id: "paper-1", title: "Denoising Diffusion Probabilistic Models", selected: true, role: "anchor" },
            { id: "paper-2", title: "Score-Based Generative Modeling through SDEs", selected: true, role: "bridge" },
            { id: "paper-3", title: "Classifier-Free Diffusion Guidance", selected: false, role: "comparison" },
          ],
          shared_concepts: [{ label: "diffusion models", paper_count: 3, paper_ids: ["paper-1", "paper-2", "paper-3"] }],
          reading_order: [
            { position: 1, paper_id: "paper-1", title: "Denoising Diffusion Probabilistic Models", reason: "Start here." },
            { position: 2, paper_id: "paper-2", title: "Score-Based Generative Modeling through SDEs", reason: "Read next." },
          ],
          comparison_axes: [
            { id: "method", label: "Method", prompt: "Compare mechanism." },
            { id: "evaluation", label: "Evaluation evidence", prompt: "Compare evidence." },
          ],
          synthesis_tasks: [
            { type: "compare", title: "Compare how each paper frames diffusion models.", evidence: ["paper-1", "paper-2"] },
            { type: "synthesize", title: "Write one synthesis paragraph.", evidence: ["paper-1", "paper-2"] },
          ],
        },
      },
    });

    render(<App />);

    const summary = screen.getByText("Paper set");
    const section = summary.closest("details")!;
    expect(section).not.toHaveAttribute("open");
    fireEvent.click(summary);
    expect(section).toHaveAttribute("open");
    expect(within(section).getAllByText("Denoising Diffusion Probabilistic Models").length).toBeGreaterThan(0);
    expect(within(section).getByText("Classifier-Free Diffusion Guidance")).toBeInTheDocument();
    expect(within(section).getByText("diffusion models")).toBeInTheDocument();
    expect(within(section).getByText("Start here.")).toBeInTheDocument();
    expect(within(section).getByText("Read next.")).toBeInTheDocument();
    expect(within(section).getByText("Evaluation evidence")).toBeInTheDocument();
    expect(within(section).getByText("Write one synthesis paragraph.")).toBeInTheDocument();
    expect(within(section).getByText("Compare evidence.")).toBeInTheDocument();
  });

  it("expands only the requested parent branches and synchronizes node context", () => {
    installPayload({
      reportKind: "paper_map",
      roadmap: {
        title: "Teaching LLMs to Plan",
        profile: { output_language: "zh-CN" },
        paper_map: {
          target: { title: "Teaching LLMs to Plan" },
          nodes: [
            {
              id: "target",
              role: "target",
              kind: "target",
              label: "Teaching LLMs to Plan",
              plain_explanation: "目标论文",
              evidence: [{ resource_title: "Target PDF", snippet: "Logical Chain-of-Thought Instruction Tuning" }],
            },
            {
              id: "background",
              role: "core",
              kind: "background",
              label: "符号规划背景",
              plain_explanation: "先理解规划为什么需要规则约束。",
              talking_point: "先交代符号规划要求每一步动作都合法。",
              evidence: [{ resource_title: "Target PDF", snippet: "symbolic planning requires valid action sequences" }],
            },
            { id: "methodology", role: "core", kind: "methodology", label: "Logical CoT 方法", plain_explanation: "用逻辑轨迹解释每一步动作。", talking_point: "再说明 Logical CoT 如何把动作选择变成可检查轨迹。" },
            { id: "resource-pddl", role: "resource", kind: "resource", label: "PDDL Notes", plain_explanation: "补充资料" },
            { id: "task-report", role: "task", kind: "task", label: "汇报任务", plain_explanation: "验收任务" },
          ],
          edges: [
            { from: "target", to: "background", label: "supports" },
            { from: "background", to: "methodology", label: "motivates" },
            { from: "methodology", to: "resource-pddl", label: "supports" },
            { from: "methodology", to: "task-report", label: "required_for" },
          ],
        },
      },
    });

    render(<App />);

    const roadmap = JSON.parse(document.getElementById("fields-study-flow-data")!.textContent!).roadmap as Roadmap;
    const nodes = createMapNodes(roadmap.paper_map!.nodes!);
    const focused = projectMap(nodes, roadmap.paper_map!.edges!, [], "methodology");
    expect(focused.nodes.find(n => n.id === "resource-pddl")).toHaveProperty("hidden", true);
    expect(focused.nodes.find(n => n.id === "task-report")).toHaveProperty("hidden", true);
    const parent = document.querySelector('[data-id="methodology"]') as HTMLElement;
    const expand = within(parent).getByRole("button", { hidden: true });
    expect(expand).toHaveAttribute("aria-label", "展开分支 Logical CoT 方法");
    fireEvent.click(expand);
    expect(within(parent).getByRole("button", { hidden: true })).toHaveAttribute("aria-expanded", "true");
    expect(document.querySelector('[data-id="resource-pddl"]')).not.toBeNull();
    expect(document.querySelector('[data-id="task-report"]')).not.toBeNull();
    act(() => { location.hash = "methodology"; window.dispatchEvent(new Event("hashchange")); });
    expect(screen.getByText("再说明 Logical CoT 如何把动作选择变成可检查轨迹。")).toBeInTheDocument();
    expect(within(document.querySelector(".context-panel") as HTMLElement).getByText("材料待补")).toBeInTheDocument();
    expect(screen.queryByText("Logical Chain-of-Thought Instruction Tuning")).not.toBeInTheDocument();
    fireEvent.click(within(parent).getByRole("button", { hidden: true }));
    expect(within(parent).getByRole("button", { hidden: true })).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelector('[data-id="resource-pddl"]')).toBeNull();
  });

  it("uses the literal paper title once and preserves safe portable reading entries", () => {
    const paperTitle = "Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning";
    installPayload({
      reportKind: "paper_lens",
      roadmap: {
        title: `学习路线: 快速理解并能够中文汇报 ${paperTitle}: ${paperTitle}`,
        profile: { goal: `快速理解并能够中文汇报 ${paperTitle}: ${paperTitle}`, output_language: "zh-CN" },
        paper_lens: {
          title: "Teaching LLMs to Plan 目标论文增强阅读器",
          latex_export: { pdf_file: "../../study-assets/reading.pdf", tex_file: "../../study-assets/reading.tex", compile_status: "ok" },
          target_papers: [{ title: paperTitle, url: "local://private-paper" }],
          explanation_summary: { granularity: "paragraph" },
          sections: [{ kind: "abstract", title: "一遍读懂论文" }],
          segments: [
            {
              id: "seg-1",
              section_kind: "abstract",
              section_title: "一遍读懂论文",
              unit: "paragraph",
              original_text: "This paragraph states the paper problem and contribution.",
            },
          ],
          inline_explanations: [{ segment_id: "seg-1", plain_meaning: "这段说明论文要解决什么问题。" }],
        },
      },
    });

    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Teaching LLMs to Plan" })).toHaveAttribute("title", paperTitle);
    expect(document.querySelectorAll("h1")).toHaveLength(1);
    expect(screen.queryByText(`快速理解并能够中文汇报 ${paperTitle}: ${paperTitle}`)).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="local://"]')).toBeNull();
    expect(screen.getByRole("link", { name: "精读 PDF" })).toHaveAttribute("href", "../../study-assets/reading.pdf");
    expect(screen.getByRole("link", { name: "TeX 源码" })).toHaveAttribute("href", "../../study-assets/reading.tex");
    const paragraph = screen.getByText("This paragraph states the paper problem and contribution.");
    expect(paragraph.closest("button")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "选择段落 1" }));
    expect(location.hash).toBe("#segment-seg-1");
  });

});
